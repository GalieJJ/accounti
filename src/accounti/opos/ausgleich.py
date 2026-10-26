"""Ausgleich offener Posten — Zahlung, Skonto mit Steuerkorrektur, Restbetrag.

Zwei Nebenwirkungen eines gezogenen Skontos werden oft vergessen und stehen deshalb
hier ausdrücklich: die Skontobuchung auf das Erlösschmälerungs- bzw.
Aufwandsminderungskonto **und** die anteilige Korrektur der Vorsteuer bzw.
Umsatzsteuer. Das Skonto verteilt sich nach den Bruttoanteilen der Rechnung auf ihre
Steuersätze; Netto und Steuer je Anteil rechnet `steuer/umsatzsteuer.py`.

Bei § 13b UStG und beim ig. Erwerb (Schlüssel 94/91, 19/18) steckt die Steuer nicht im
Zahlbetrag: Ihr Anteil am Skonto richtet sich nach dem Netto, und das Skonto mindert mit
demselben Schlüssel Bemessungsgrundlage, Steuer und Vorsteuer (§ 17 Abs. 1 Satz 1, 2
UStG; Steuer aus dem Netto, ``buchung/steuergruppe.py``) — auf dem Skontokonto ohne
Steuersatz (``skonto_erhalten["0"]``), denn die Konten je Satz sind
Vorsteuer-Automatikkonten.

Ein Anteil mindert den Rest des Postens um seinen Betrag (Vorzeichen des Postens). Ist
er negativ — die Erstattung einer Gutschrift oder eines Guthabens, oder die Gutschrift
in einer Saldozahlung —, fließt das Geld in die Gegenrichtung und die Buchung dreht
sich um. Der Gutschriftanteil einer Saldozahlung heißt „Verrechnung“: Er steht als
eigene Bankbuchung gegen die Zahlung (595 € herein, 119 € hinaus = 476 € auf dem
Auszug), es fließt aber nichts zurück. Eine Überzahlung schließt den Posten nicht: Sein
Rest wird negativ und steht als Guthaben des Kontakts in der Postenliste, so wie auf dem
Personenkonto.
"""

from __future__ import annotations

from collections import defaultdict
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy.orm import Session

from accounti.buchung.steuergruppe import SELBST_BERECHNET, selbst_berechnete_steuer
from accounti.db.repository import (
    aktualisiere_posten,
    lade_belegbuchungen,
    lade_einen_posten,
    lade_kontakt,
    speichere_buchung,
)
from accounti.konfiguration import Buchhaltung
from accounti.models import (
    Buchungssatz,
    BuchungStatus,
    OffenerPosten,
    PostenRichtung,
    PostenStatus,
    Transaktion,
)
from accounti.opos.zuordnung import Anteil
from accounti.steuer.kennziffern import STEUERSCHLUESSEL
from accounti.steuer.umsatzsteuer import UStBerechner

NULL = Decimal("0")
CENT = Decimal("0.01")
# BU-Schlüssel der Rechnungsbuchungen → Steuersatz
_SATZ_AUS_SCHLUESSEL = {
    9: Decimal("19"),
    3: Decimal("19"),
    8: Decimal("7"),
    2: Decimal("7"),
}
_VST_SCHLUESSEL = {Decimal("19"): 9, Decimal("7"): 8}
_UST_SCHLUESSEL = {Decimal("19"): 3, Decimal("7"): 2}


def _bruttoanteile(
    session: Session, posten: OffenerPosten
) -> list[tuple[Decimal, int | None, Decimal]]:
    """(Steuersatz, Schlüssel bei § 13b/ig. Erwerb, Anteil am Zahlbetrag) der Rechnung
    hinter dem Posten, aus ihren Buchungen — brutto, bei § 13b und ig. Erwerb nur das
    Netto (die Steuer schuldet der Empfänger selbst, sie steckt nicht im Posten)."""
    anteile: dict[tuple[Decimal, int | None], Decimal] = defaultdict(lambda: NULL)
    for b in lade_belegbuchungen(session, posten.beleg_id):
        schluessel = b.steuer_schluessel or 0
        if schluessel in SELBST_BERECHNET:
            satz = STEUERSCHLUESSEL[schluessel].satz
            anteile[(satz, schluessel)] += b.betrag_netto
            continue
        satz = _SATZ_AUS_SCHLUESSEL.get(schluessel, NULL)
        anteile[(satz, None)] += b.betrag_netto + (b.steuer_betrag or NULL)
    if not anteile:
        return [(NULL, None, abs(posten.betrag))]
    return sorted(
        ((satz, s, brutto) for (satz, s), brutto in anteile.items()),
        key=lambda a: (-a[0], a[1] or 0),
    )


def _skonto_buchungen(
    session: Session,
    tx: Transaktion,
    posten: OffenerPosten,
    skonto: Decimal,
    personenkonto: str,
    einstellungen: Buchhaltung,
    text: str,
    status: BuchungStatus,
    geprueft_von: str | None = None,
) -> list[Buchungssatz]:
    eingang = posten.richtung is PostenRichtung.VERBINDLICHKEIT
    konten = einstellungen.skonto_erhalten if eingang else einstellungen.skonto_gewaehrt
    anteile = _bruttoanteile(session, posten)
    gesamt = sum((brutto for _, _, brutto in anteile), NULL)
    berechner = UStBerechner()

    buchungen = []
    verteilt = NULL
    for i, (satz, selbst, brutto) in enumerate(anteile):
        if i == len(anteile) - 1:
            teil = skonto - verteilt  # Rundungsrest auf den letzten Satz
        else:
            teil = (skonto * brutto / gesamt).quantize(CENT, rounding=ROUND_HALF_UP)
        verteilt += teil
        if teil == 0:
            continue
        konto = konten.get(str(satz.normalize()), konten["0"])
        schluessel: int | None
        if selbst is not None:
            # § 13b / ig. Erwerb: das Skonto ist Netto, Steuer und Vorsteuer mindern
            # sich mit demselben Schlüssel
            schluessel, konto = selbst, konten["0"]
            netto, steuer = teil, selbst_berechnete_steuer(selbst, teil)
        elif (
            schluessel := (_VST_SCHLUESSEL if eingang else _UST_SCHLUESSEL).get(satz)
        ) is not None:
            # Vorsteuer- bzw. Umsatzsteuerkorrektur aus steuer/
            korrektur = berechner.berechne_vst(teil, satz)
            netto, steuer = korrektur.netto, korrektur.steuerbetrag
        else:
            netto, steuer = teil, None
        soll, haben = (personenkonto, konto) if eingang else (konto, personenkonto)
        buchung = Buchungssatz(
            transaktion_id=tx.id,
            beleg_id=posten.beleg_id,
            datum=tx.datum,
            soll_konto=soll,
            haben_konto=haben,
            betrag_netto=netto,
            steuer_schluessel=schluessel,
            steuer_betrag=steuer,
            buchungstext=f"Skonto {text}"[:60],
            beleg_nummer=posten.belegnummer,
            status=status,
            confidence=1.0,
            geprueft_von=geprueft_von,
        )
        speichere_buchung(session, buchung)
        buchungen.append(buchung)
    return buchungen


def gleiche_aus(
    session: Session,
    tx: Transaktion,
    anteile: list[Anteil],
    einstellungen: Buchhaltung,
    status: BuchungStatus = BuchungStatus.AUTO_GEBUCHT,
    geprueft_von: str | None = None,
) -> list[Buchungssatz]:
    """Bucht Zahlung (und ggf. Skonto) je Anteil und mindert die Posten
    (``geprueft_von``: wer einen Vorschlag bestätigt hat).

    Die Posten werden frisch geladen: Maßgeblich ist der aktuelle Restbetrag, nicht
    der Stand zum Zeitpunkt des Vorschlags.
    """
    buchungen: list[Buchungssatz] = []
    for anteil in anteile:
        posten = lade_einen_posten(session, anteil.posten.id)
        if posten.status is PostenStatus.AUSGEGLICHEN:
            msg = f"Posten {posten.belegnummer} ist bereits ausgeglichen."
            raise ValueError(msg)
        kontakt = lade_kontakt(session, str(posten.kontakt_id))
        eingang = posten.richtung is PostenRichtung.VERBINDLICHKEIT
        personenkonto = kontakt.kreditor_konto if eingang else kontakt.debitor_konto
        # Erstattung eines Kreditors (z. B. Finanzamt) bzw. Rückzahlung an einen
        # Debitor: der Posten steht auf dem einzigen Personenkonto des Kontakts
        personenkonto = personenkonto or (
            kontakt.debitor_konto if eingang else kontakt.kreditor_konto
        )
        if personenkonto is None:
            msg = f"{kontakt.name} hat kein Personenkonto für diesen Posten."
            raise ValueError(msg)
        text = f"{posten.belegnummer or ''} {kontakt.name}".strip()
        bank = tx.sachkonto or einstellungen.bank_konto  # Konto des Umsatzes
        # Geld kommt herein: Forderung wird kleiner oder ein Guthaben beim Kreditor
        # wird erstattet — sonst geht es hinaus
        herein = (anteil.betrag > 0) != eingang
        soll, haben = (bank, personenkonto) if herein else (personenkonto, bank)
        if anteil.betrag != 0:
            # gegen die Zahlung: der Gutschrift- oder Guthabenanteil einer
            # Saldozahlung — verrechnet, nicht erstattet (es fließt kein Geld zurück)
            if herein != (tx.betrag > 0):
                art = "Verrechnung"
            else:
                art = "Zahlung" if anteil.betrag > 0 else "Erstattung"
            zahlung = Buchungssatz(
                transaktion_id=tx.id,
                beleg_id=posten.beleg_id,
                datum=tx.datum,
                soll_konto=soll,
                haben_konto=haben,
                betrag_netto=abs(anteil.betrag),
                buchungstext=f"{art} {text}"[:60],
                beleg_nummer=posten.belegnummer,
                status=status,
                confidence=1.0,
                geprueft_von=geprueft_von,
            )
            speichere_buchung(session, zahlung)
            buchungen.append(zahlung)
        if anteil.skonto > 0:
            buchungen += _skonto_buchungen(
                session,
                tx,
                posten,
                anteil.skonto,
                personenkonto,
                einstellungen,
                text,
                status,
                geprueft_von,
            )
        # Überzahlung: der Rest wird negativ — das Guthaben bleibt ein offener Posten
        # und stimmt so mit dem Personenkonto überein
        rest = posten.restbetrag - anteil.betrag - anteil.skonto
        aktualisiere_posten(
            session,
            posten.id,
            rest,
            PostenStatus.AUSGEGLICHEN if rest == 0 else PostenStatus.TEILBEZAHLT,
        )
    return buchungen
