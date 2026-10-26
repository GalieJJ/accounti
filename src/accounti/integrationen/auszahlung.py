"""Auszahlung ↔ Bankumsatz: der einzige Abgleichspunkt einer Abrechnung.

Die Regel, welcher Bankumsatz zu welcher Auszahlung gehört, in einem Stück
(``_umsaetze``, ``_kandidaten``, ``_befund``, ``_zweifel``, ``ordne_zu``;
Nachprüfungen 1–5 E):

1. In Frage kommen Bankumsätze im Zeitfenster um das Auszahlungsdatum mit derselben
   Richtung, die weder früher noch in diesem Lauf einem Marktplatzposten zugeordnet
   sind — nie PayPal-Umsätze, Umsätze auf einem Verrechnungskonto oder einer, dessen
   Zuordnung zu dieser Auszahlung von Hand gelöst ist (Regel 9).
2. Nummer vor Betrag: Nennt ein Umsatz die Nummer einer anderen bekannten Abrechnung
   desselben Marktplatzes (gespeichert oder aus demselben Bericht; als eigenes Wort,
   mindestens 6 Zeichen) und nicht die eigene, gehört er zu ihr — hier weder Treffer
   noch Befund.
3. Nennt ein Umsatz im Fenster die eigene Nummer, zählen nur die eigenen, ob offen,
   als Erlös gebucht oder umgebucht: Kein anderer wird Treffer, auch nicht mit
   exaktem Betrag oder in der Toleranz, und keiner der anderen steht im Befund. Ein
   Umsatz ohne die eigene Nummer kann nur Treffer werden, wenn keiner sie nennt.
4. Nennt ein offener Umsatz statt der eigenen eine andere Nummer derselben Form, die
   noch keine Abrechnung trägt, ist er wohl die Auszahlung einer noch nicht
   importierten: weder Treffer noch Abweichung. Dieselbe Form heißt: nur Ziffern,
   gleiche Länge, dieselben zwei ersten Ziffern (die Nummern eines Marktplatzes
   laufen fort) und nicht hinter einer Kunden-, Mandats-, Konto- oder
   Rechnungsangabe (KD, Kunden-Nr., MREF, IBAN …) — eine Referenz der Bank mit
   anderem Anfang (EREF 4711000815 neben 6009990001) oder eine Kundennummer zählt
   nicht (Nachprüfung 5 E, M4). Eine EREF mit demselben Anfang zählt: Marktplätze
   setzen dort ihre Auszahlungsnummer. Bleibt sonst nichts, ist das die Warnung
   ``auszahlung_andere_nummer`` mit dem Befehl aus Regel 9; mit dem Import jener
   Abrechnung gilt Regel 2, die Warnung erledigt sich. Ist er schon gebucht, sagt der
   Befund „schon gebucht“ dazu, dass er wohl zu einer anderen gehört; hat der Mensch
   ihn danach selbst aufs Gegenkonto gebucht, gilt das (Regel 5).
5. Treffer ist ein offener Umsatz — oder einer, der als Geldbewegung schon auf dem
   Gegenkonto steht (die Korrektur nach „schon gebucht“, ``_vorgebucht``) — mit exakt
   dem erwarteten Betrag, in Fremdwährung ohne solchen einer mit Stichwort oder
   Nummer in der Toleranz. Mehrere grenzen Stichwort und eigene Nummer ein; bleiben
   mehrere, ist das ``auszahlung_mehrdeutig`` — es wird nicht geraten. Ebenso, wenn
   derselbe Umsatz der einzige Kandidat der Auszahlungen mehrerer Abrechnungen ist:
   keine bekommt ihn, jede warnt. Deshalb gleicht auch der Import einer einzelnen
   Abrechnung alle ab, ein Bericht mit mehreren erst, wenn alle gespeichert sind.
   Nennt der Treffer die eigene Nummer nicht, ist die Zuordnung
   geraten — das sagt ein Hinweis (``zuordnung_ohne_nummer``) mit dem Befehl aus
   Regel 9.
6. Ohne Treffer gilt der erste dieser Befunde: ein als Erlös gebuchter mit passendem
   Betrag (``auszahlung_anderweitig_gebucht``, Fehler — die Voranmeldung des
   Bankmonats warnt, ``bankdaten``; mehrere grenzen eigene Nummer, keine andere
   Nummer und exakter Betrag ein, sonst nennt der Befund alle) — ebenso einer mit der
   eigenen Nummer außerhalb der Toleranz (falscher Kurs, Teilbetrag: der Erlös ist
   trotzdem doppelt, Nachprüfung 5 E, N2); ein offener Umsatz mit Stichwort oder
   Nummer in anderer Höhe oder der eigene als Geldbewegung außerhalb der Toleranz
   (``auszahlung_abweichung``); eine Geldbewegung auf einem anderen Konto
   (``auszahlung_umgebucht``); Regel 4. Sonst ist die Auszahlung noch nicht auf der
   Bank, ohne Befund.
7. Befunde über einen Umsatz (``_UMSATZBEFUNDE``) gelten, solange ein Lauf sie so
   wiederfindet — nennt ein späterer einen anderen oder keinen Umsatz mehr (etwa weil
   die fremde Nummer inzwischen bekannt ist), ist der alte erledigt; „mehrdeutig“
   und „abweichung“ ersetzt ein neuer Text, und findet ein Lauf gar nichts mehr,
   sind alle erledigt. Ein Treffer erledigt alle Abgleichsbefunde des Postens.
8. Eine Zuordnung zu einem Umsatz ohne die eigene Nummer (als noch keiner sie
   nannte) bezweifelt der Abgleich, sobald im Fenster einer mit der Nummer steht —
   als Erlös gebucht ist das ``auszahlung_anderweitig_gebucht`` (die Voranmeldung
   seines Monats warnt), offen oder als Geldbewegung auf dem Gegenkonto die Warnung
   ``auszahlung_zweifel`` — oder sobald der zugeordnete Umsatz die Nummer einer
   inzwischen bekannten anderen Abrechnung nennt (ebenfalls ``auszahlung_zweifel``).
   Die Zuordnung bleibt; der Befund nennt den Befehl aus Regel 9. Eine Zuordnung von
   Hand bezweifelt nur der doppelte Erlös.
9. ``accounti marktplatz zuordnen <Nummer> <Umsatz>`` (``ordne_zu``) ordnet
   ausdrücklich zu, wo der Abgleich nicht entscheidet; eine bisherige Zuordnung des
   Umsatzes oder der Auszahlung wird dabei gelöst (accountis Bankbuchung storniert),
   danach gleicht accounti alles neu ab. ``--loesen`` löst nur: der Umsatz gehört
   nicht zu dieser Auszahlung, der Abgleich nimmt ihn hier nicht wieder (Regel 1).
   Ein als Erlös gebuchter Umsatz wird erst korrigiert (``accounti korrigiere``).

Zusammenspiel mit der Kontierung (``buchung.marktplatz``): ``classify`` und ``bank
lauf`` lassen einen Eingang mit Stichwort offen, solange keine Abrechnung ihn
abgeglichen hat, und ebenso jeden Umsatz, den eine importierte Abrechnung noch
erwartet — auch mit einem Befund dieses Abgleichs. ``bank lauf`` kontiert keinen
Umsatz, über den der Abgleich desselben Laufs einen Befund hat, auch nicht aus einem
Beleg (``Abgleich.umsaetze``). Als Erlös gebucht („schon gebucht“, Regeln 6 und 8)
ist eine Auszahlung deshalb nur von Hand, ohne Stichwort (``bank_stichworte: []``
oder ein Verwendungszweck ohne) oder aus der Zeit vor dieser Regel.

Grenzen: Ohne Nummer im Verwendungszweck entscheiden Stichwort und Betrag — die
Zuordnung ist geraten (Hinweis, Regel 5): welcher von zwei Umsätzen in der Toleranz
zu welcher Auszahlung gehört (die Kursdifferenzen sind vertauscht, ihre Summe
stimmt), und ein Umsatz ohne Nummer kann Treffer werden, bevor der mit der eigenen
Nummer auf der Bank steht (dann Regel 8). Richtig stellt das ``marktplatz zuordnen``.
Eine Bankreferenz mit denselben zwei ersten Ziffern hält Regel 4 zurück (Warnung,
Regel 9). In Fremdwährung findet der Abgleich eine Auszahlung ohne Stichwort und
ohne Nummer gar nicht — ohne Befund, die Kontierung bucht sie dann nach den Regeln;
``bank_stichworte`` deshalb nur leeren, wer keine Abrechnungen importiert (sonst warnt
der Import: ``bank_stichworte_leer``).

Fremdwährung: Die Abrechnung rechnet jeden Posten mit dem eingegebenen Kurs um, die
Bank schreibt den Betrag gut, den sie selbst umgerechnet hat — exakt gleich ist das
fast nie. Deshalb gilt dort ``auszahlung_toleranz_prozent``; gebucht wird der
Bankbetrag, die Differenz geht auf die Kursdifferenzkonten (Aufwand bzw. Ertrag aus
der Währungsumrechnung, ohne Umsatzsteuer — der Umsatz ist mit dem Kurs der
Abrechnung bemessen, § 16 Abs. 6 UStG).

Steht ein Umsatz schon auf dem Verrechnungskonto dieser Abrechnung — etwa nach der
Korrektur, die der Befund „anderweitig gebucht“ vorschlägt —, wird nur noch die
Kursdifferenz gebucht, die dort stehen bliebe. Sonst wird „Bank an
Verrechnungskonto“ (PayPal: Bank an Geldtransit) mit der ``transaktion_id`` des
Bankumsatzes gebucht — damit lässt ``classify`` ihn in Ruhe.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy.orm import Session

from accounti.db.repo_integrationen import (
    abrechnungsnummern,
    ergaenze_befunde,
    erledige_befunde,
    lade_abrechnung,
    lade_abrechnungen,
    setze_abrechnungsstatus,
    setze_bank_transaktion,
    zugeordnete_bank_transaktionen,
)
from accounti.db.repository import (
    buchungen_zur_transaktion,
    gebuchte_transaktion_ids,
    lade_transaktionen,
    speichere_buchung,
)
from accounti.integrationen.buchung import ANZEIGE, eur_text
from accounti.integrationen.einstellungen import Kontext
from accounti.models import Buchungssatz, BuchungStatus, Transaktion, TransaktionQuelle
from accounti.models.integrationen import (
    Abrechnung,
    AbrechnungStatus,
    Befund,
    Marktplatzposten,
    Postenart,
    Schweregrad,
)
from accounti.opos.zahlungslauf import offene_transaktionen

if TYPE_CHECKING:
    from accounti.abschluss.kontenrahmen import Kontenrahmen

VORLAUF = timedelta(days=2)  # Bank bucht selten vor dem gemeldeten Auszahlungsdatum


@dataclass
class Abgleich:
    abrechnung: Abrechnung
    posten: Marktplatzposten
    transaktion: Transaktion | None = None
    befund: Befund | None = None
    # die Bankumsätze, von denen der Befund spricht — ``bank lauf`` kontiert sie im
    # selben Lauf nicht (Nachprüfung 5 E, M4 a)
    umsaetze: list[Transaktion] = field(default_factory=list)


ABGLEICHSBEFUNDE = {
    "auszahlung_abweichung",
    "auszahlung_mehrdeutig",
    "auszahlung_anderweitig_gebucht",
    "auszahlung_umgebucht",
    "auszahlung_andere_nummer",
    "auszahlung_zweifel",
}
# Befunde über einen bestimmten Umsatz: überholt, sobald ein Lauf ihn nicht mehr so
# findet (``gleiche_auszahlungen_ab``, Regel 7)
_UMSATZBEFUNDE = {
    "auszahlung_anderweitig_gebucht",
    "auszahlung_umgebucht",
    "auszahlung_andere_nummer",
    "auszahlung_zweifel",
}
# Text des Befunds „auszahlung_anderweitig_gebucht“ — ``bankdaten`` liest die Tage
# daraus zurück; beides nur hier ändern
_SCHON_GEBUCHT = "Der Bankumsatz vom {tag:%d.%m.%Y} ist schon gebucht"
_SCHON_GEBUCHT_TAG = re.compile(
    r"Der Bankumsatz vom (\d{2})\.(\d{2})\.(\d{4}) ist schon gebucht"
)
_SCHON_GEBUCHT_MEHRERE = "schon gebuchte Bankumsätze passen"
_TAG = re.compile(r"vom (\d{2})\.(\d{2})\.(\d{4})")
_ZIFFERN = re.compile(r"[0-9]+")
_WORT = re.compile(r"[0-9A-Z]+")
# kürzere Nummern stehen zu leicht zufällig in einem Verwendungszweck, um einen
# Umsatz deshalb einer anderen Abrechnung zuzuschreiben
_MINDESTLAENGE = 6
# Regel 4: Auszahlungsnummern eines Marktplatzes laufen fort (6009990001,
# 6009990002; Settlement-IDs) — eine Zahl derselben Länge mit anderem Anfang ist eine
# Referenz der Bank (EREF 4711000815), keine Auszahlungsnummer (Nachprüfung 5 E, M4)
_ANFANG = 2
# Bezeichnungen, hinter denen eine Zahl Kunden-, Mandats-, Konto-, Vertrags- oder
# Rechnungsangabe ist, nie eine Auszahlungsnummer (KD 40123456789, Kunden-Nr. …)
_REFERENZEN = frozenset(
    {
        "KD",
        "KDN",
        "KDNR",
        "KNR",
        "KUNDE",
        "KUNDEN",
        "KUNDENNR",
        "KUNDENNUMMER",
        "MANDAT",
        "MANDATS",
        "MANDATSREF",
        "MANDATSREFERENZ",
        "MREF",
        "KREF",
        "CRED",
        "IBAN",
        "BIC",
        "KONTO",
        "KTO",
        "KTONR",
        "BLZ",
        "VERTRAG",
        "VERTRAGSNR",
        "RECHNUNG",
        "RECHNUNGSNR",
        "RE",
        "RG",
        "RGNR",
    }
)
_NR = frozenset({"NR", "NO", "NUMMER"})
# Hinweise an der Abrechnung (keine Abgleichsbefunde): eine Zuordnung ohne die
# Nummer im Verwendungszweck (geraten), eine von Hand und eine von Hand gelöste
OHNE_NUMMER = "zuordnung_ohne_nummer"
VON_HAND = "zuordnung_von_hand"
GELOEST = "zuordnung_geloest"
_UMSATZ_ID = re.compile(r"\[Umsatz ([0-9a-f-]{36})\]")


def bankdaten(befund: Befund) -> list[date]:
    """Tage der schon gebuchten Bankumsätze eines Befunds
    ``auszahlung_anderweitig_gebucht`` — dort steht die Fehlbuchung und damit der
    doppelte Erlös in der Voranmeldung, nicht im Zeitraum der Abrechnung (z. B.
    Abrechnung 16.–31.08., Auszahlung am 03.09.). Passen mehrere Umsätze, nennt der
    Befund alle (es wird nicht geraten), die Voranmeldung jedes Tages warnt. Die
    Tabelle ``marktplatz_befunde`` hat keine Spalte dafür, die Tage stehen im
    Befundtext; leer bei anderen Befunden oder einem Text ohne Tag."""
    if befund.code != "auszahlung_anderweitig_gebucht":
        return []
    einer = _SCHON_GEBUCHT_TAG.search(befund.text)
    if einer is not None:
        treffer = [einer]
    elif _SCHON_GEBUCHT_MEHRERE in befund.text:
        kopf = befund.text.split(" — ", 1)[0]
        treffer = list(_TAG.finditer(kopf))
    else:
        return []
    tage = []
    for t in treffer:
        tag, monat, jahr = (int(x) for x in t.groups())
        try:
            tage.append(date(jahr, monat, tag))
        except ValueError:
            continue
    return tage


def bankdatum(befund: Befund) -> date | None:
    """Erster Tag aus ``bankdaten`` (``None``, wenn der Befund keinen nennt)."""
    tage = bankdaten(befund)
    return tage[0] if tage else None


def status_von(abrechnung: Abrechnung) -> AbrechnungStatus:
    """Status aus den offenen Befunden und den noch nicht abgeglichenen Posten."""
    if any(b.schweregrad is Schweregrad.FEHLER for b in abrechnung.offene_befunde):
        return AbrechnungStatus.ABWEICHUNG
    if not abrechnung.vollstaendig:
        return AbrechnungStatus.GEBUCHT  # die Auszahlung steht noch aus
    offen = [
        p
        for p in abrechnung.posten
        if p.art in (Postenart.AUSZAHLUNG, Postenart.EINZAHLUNG)
        and p.bank_transaktion_id is None
        and (p.betrag or p.betrag_eur)
    ]
    return AbrechnungStatus.GEBUCHT if offen else AbrechnungStatus.ABGEGLICHEN


@dataclass
class _Lauf:
    """Gemeinsamer Stand eines Abgleichslaufs über mehrere Abrechnungen."""

    session: Session
    kontext: Kontext
    bankumsaetze: list[Transaktion]
    offen_ids: set[UUID]
    gebucht: set[UUID]
    # schon einem Marktplatzposten zugeordnet (frühere Läufe) — nie „schon gebucht“
    zugeordnet: set[UUID]
    # Verrechnungs-, Geldtransit- und Kursdifferenzkonten: Geldbewegung, kein Erlös
    geldkonten: set[str]
    # bekannte Abrechnungsnummern je Marktplatz (gespeichert und aus dem Bericht)
    nummern: dict[str, set[str]] = field(default_factory=dict)
    benutzt: set[UUID] = field(default_factory=set)
    buchungen: dict[UUID, list[Buchungssatz]] = field(default_factory=dict)
    genannt: dict[tuple[UUID, str], set[str]] = field(default_factory=dict)
    # Wort im Verwendungszweck → Umsätze (Regel 8, erst bei Bedarf gebaut)
    woerter: dict[str, list[Transaktion]] | None = None
    # Posten → Umsätze, deren Zuordnung von Hand gelöst ist (Regel 9)
    ausgeschlossen: dict[UUID, set[UUID]] = field(default_factory=dict)
    # Posten, die von Hand zugeordnet sind — Regel 8 zweifelt dort nur bei Erlös
    von_hand: set[UUID] = field(default_factory=set)
    # Posten → die anderen Abrechnungen, deren Auszahlung denselben einzigen
    # Kandidaten hat (Regel 5: nicht raten)
    umstritten: dict[UUID, list[Abrechnung]] = field(default_factory=dict)


def _neuer_lauf(
    session: Session,
    kontext: Kontext,
    abrechnungen: list[Abrechnung],
    nummern: Iterable[tuple[str, str]] = (),
) -> _Lauf:
    """Stand eines Laufs: Bankumsätze, Buchungs- und Zuordnungsstand, bekannte
    Nummern, von Hand gelöste und von Hand gesetzte Zuordnungen."""
    e = kontext.einstellungen
    bekannt = abrechnungsnummern(session)
    for markt, nummer in [*((a.marktplatz, a.nummer) for a in abrechnungen), *nummern]:
        bekannt.setdefault(markt, set()).add(nummer)
    marktkonten = {k.verrechnungskonto for k in e.marktplaetze.values()}
    lauf = _Lauf(
        session=session,
        kontext=kontext,
        bankumsaetze=[
            t
            for t in lade_transaktionen(session)
            if t.quelle is not TransaktionQuelle.PAYPAL
            and (t.sachkonto or kontext.buchhaltung.bank_konto) not in marktkonten
        ],
        offen_ids={t.id for t in offene_transaktionen(session, fuer_kontierung=True)},
        gebucht=gebuchte_transaktion_ids(session),
        zugeordnet=zugeordnete_bank_transaktionen(session),
        geldkonten=marktkonten
        | {e.geldtransit_konto, e.kursdifferenz_ertrag, e.kursdifferenz_aufwand},
        nummern=bekannt,
    )
    for a in abrechnungen:
        posten = {p.nr: p.id for p in a.posten}
        for b in a.offene_befunde:
            ident = posten.get(b.posten_nr) if b.posten_nr is not None else None
            if ident is None:
                continue
            if b.code == GELOEST and (umsatz := _UMSATZ_ID.search(b.text)):
                lauf.ausgeschlossen.setdefault(ident, set()).add(UUID(umsatz[1]))
            elif b.code == VON_HAND:
                lauf.von_hand.add(ident)
    return lauf


def _erwartet(a: Abrechnung, p: Marktplatzposten) -> Decimal | None:
    """Erwarteter Bankbetrag des Postens (Vorzeichen der Bank) — ``None`` in
    Fremdwährung ohne Kurs (nicht gebucht, also nicht abzugleichen) oder bei 0."""
    if a.waehrung != "EUR" and p.betrag_eur is None:
        return None
    erwartet = -(p.betrag_eur if p.betrag_eur is not None else p.betrag)
    return erwartet or None


def gleiche_auszahlungen_ab(
    session: Session,
    kontext: Kontext,
    abrechnungen: list[Abrechnung] | None = None,
    nummern: Iterable[tuple[str, str]] = (),
) -> list[Abgleich]:
    """Gleicht offene Auszahlungen (und PayPal-Einzahlungen) mit der Bank ab.

    Erst werden alle eindeutigen exakten Treffer zugeordnet — wiederholt, weil jeder
    Treffer die Kandidaten der übrigen verkleinert —, danach erst Befunde für den
    Rest gebildet. So ist ein Umsatz, den im selben Lauf eine andere Auszahlung
    bekommen hat, für niemanden eine Abweichung, unabhängig von der Reihenfolge.

    ``nummern``: (Marktplatz, Nummer) weiterer Abrechnungen desselben Berichts, die
    noch nicht gespeichert sind — ein Umsatz mit einer davon gehört nicht hierher.

    ``abrechnungen`` (der Import einer Abrechnung): Abgeglichen werden trotzdem alle
    — mit ihr kann ein Befund einer anderen erledigt sein (Regel 2: die Nummer ist
    jetzt bekannt), und ein Umsatz, den beide als einzigen Kandidaten haben, gehört
    keiner (Regel 5). Zurück kommen nur die Ergebnisse der übergebenen.

    Ergebnis: je offenem Posten ein ``Abgleich``, dazu einer (ohne ``transaktion``)
    für jede frühere Zuordnung, die Regel 8 jetzt bezweifelt.
    """
    alle = lade_abrechnungen(session)
    gefragt = {a.id for a in abrechnungen} if abrechnungen is not None else None
    if abrechnungen is not None:
        uebergeben = {a.id: a for a in abrechnungen}
        abrechnungen = [uebergeben.pop(a.id, a) for a in alle] + list(
            uebergeben.values()
        )
    else:
        abrechnungen = alle
    lauf = _neuer_lauf(session, kontext, abrechnungen, nummern)
    offene = _offene_posten(abrechnungen)

    ergebnisse: dict[UUID, Abgleich] = {}
    weiter = True
    while weiter:
        weiter = False
        einzig: dict[UUID, list[tuple[Abrechnung, Marktplatzposten, Decimal]]] = {}
        treffer: dict[UUID, Transaktion] = {}
        for a, p, erwartet in offene:
            if p.id in ergebnisse:
                continue
            kandidaten = _kandidaten(lauf, a, p, erwartet)
            if len(kandidaten) == 1:
                einzig.setdefault(kandidaten[0].id, []).append((a, p, erwartet))
                treffer[kandidaten[0].id] = kandidaten[0]
        for ident, anwaerter in einzig.items():
            # Regel 5: ist derselbe Umsatz der einzige Kandidat der Auszahlungen
            # mehrerer Abrechnungen, entscheidet nichts zwischen ihnen
            abrechnungen_hier = {a.id: a for a, _p, _e in anwaerter}
            if len(abrechnungen_hier) > 1:
                for _a, p, _e in anwaerter:
                    lauf.umstritten[p.id] = [
                        x for x in abrechnungen_hier.values() if x.id != _a.id
                    ]
                continue
            a, p, erwartet = anwaerter[0]
            lauf.umstritten.pop(p.id, None)
            ergebnisse[p.id] = _zuordnen(lauf, a, p, treffer[ident], erwartet)
            weiter = True
    neue_befunde: dict[UUID, list[Befund]] = {}
    ueberholt: list[Befund] = []
    for a, p, erwartet in offene:
        if p.id not in ergebnisse:
            ergebnis = _befund(lauf, a, p, erwartet)
            ergebnisse[p.id] = ergebnis
            neu = ergebnis.befund
            if neu is not None:
                neue_befunde.setdefault(a.id, []).append(neu)
            ueberholt.extend(
                b
                for b in a.offene_befunde
                if b.posten_nr == p.nr and _ueberholt(b, neu)
            )
    # Regel 8: Zuordnungen früherer Läufe ohne die eigene Nummer gegen Umsätze, die
    # sie nennen, oder mit der Nummer einer inzwischen bekannten anderen Abrechnung
    zweifel: list[Abgleich] = []
    for a in abrechnungen:
        for p in a.posten:
            if (
                p.art not in (Postenart.AUSZAHLUNG, Postenart.EINZAHLUNG)
                or p.bank_transaktion_id is None
                or p.id in ergebnisse
            ):
                continue
            gefunden = _zweifel(lauf, a, p)
            neu = gefunden[0] if gefunden is not None else None
            if gefunden is not None:
                neue_befunde.setdefault(a.id, []).append(gefunden[0])
                zweifel.append(Abgleich(a, p, befund=gefunden[0], umsaetze=gefunden[1]))
            ueberholt.extend(
                b
                for b in a.offene_befunde
                if b.code in _UMSATZBEFUNDE
                and b.posten_nr == p.nr
                and (neu is None or (b.code, b.text) != (neu.code, neu.text))
            )
    for b in ueberholt:
        b.erledigt = True
    erledige_befunde(session, [b.id for b in ueberholt])

    erledigt = {b.id for b in ueberholt}
    betroffen = {a.id: a for a, _p, _e in offene}
    betroffen.update(
        (a.id, a)
        for a in abrechnungen
        if a.id in neue_befunde or any(b.id in erledigt for b in a.befunde)
    )
    for a in betroffen.values():
        befunde = neue_befunde.get(a.id, [])
        if befunde:
            ergaenze_befunde(session, a.id, befunde)
            a.befunde.extend(befunde)
        a.status = status_von(a)
        setze_abrechnungsstatus(session, a.id, a.status)
    return [
        x
        for x in [*(ergebnisse[p.id] for _a, p, _e in offene), *zweifel]
        if gefragt is None or x.abrechnung.id in gefragt
    ]


def _offene_posten(
    abrechnungen: Iterable[Abrechnung],
) -> list[tuple[Abrechnung, Marktplatzposten, Decimal]]:
    """Aus- und Einzahlungen ohne Bankumsatz, mit ihrem erwarteten Bankbetrag."""
    offene = []
    for a in abrechnungen:
        for p in a.posten:
            if (
                p.art not in (Postenart.AUSZAHLUNG, Postenart.EINZAHLUNG)
                or p.bank_transaktion_id is not None
            ):
                continue
            erwartet = _erwartet(a, p)
            if erwartet is not None:
                offene.append((a, p, erwartet))
    return offene


def _ueberholt(alt: Befund, neu: Befund | None) -> bool:
    """Regel 7: Ist ein älterer Abgleichsbefund eines offenen Postens überholt?

    Findet der Lauf nichts mehr, alle. „Schon gebucht“, „umgebucht“, „andere
    Nummer“ gelten, solange der Lauf denselben Umsatz findet: nennt er einen anderen
    oder keinen mehr, sind sie überholt (etwa weil der Umsatz die Nummer einer
    inzwischen bekannten Abrechnung trägt) — nach „mehrdeutig“ nicht, dort wird nach
    gebuchten nicht gesucht. „Mehrdeutig“ und „abweichung“ ersetzt ein neuer Text
    desselben Befunds."""
    if alt.code not in ABGLEICHSBEFUNDE:
        return False
    if neu is None:
        return True
    if (alt.code, alt.text) == (neu.code, neu.text):
        return False
    if alt.code in _UMSATZBEFUNDE:
        return neu.code != "auszahlung_mehrdeutig"
    return alt.code == neu.code


def _fenster(lauf: _Lauf, p: Marktplatzposten) -> tuple[date, date]:
    toleranz = timedelta(days=lauf.kontext.einstellungen.auszahlung_toleranz_tage)
    return p.datum - VORLAUF, p.datum + toleranz


def _text(t: Transaktion) -> str:
    return f"{t.verwendungszweck} {t.gegenkonto_name or ''}".upper()


def _erkennbar(lauf: _Lauf, a: Abrechnung, t: Transaktion) -> bool:
    konten = lauf.kontext.einstellungen.marktplatz(a.marktplatz)
    text = _text(t)
    return (
        any(w.upper() in text for w in konten.bank_stichworte)
        or a.nummer.upper() in text
    )


def _nennt(text: str, nummer: str) -> bool:
    """``nummer`` steht als eigenes Wort im (großgeschriebenen) Text — nicht als Teil
    einer längeren Nummer (6009990001 nicht in 60099900012)."""
    gesucht = nummer.upper()
    start = text.find(gesucht) if gesucht else -1
    while start >= 0:
        ende = start + len(gesucht)
        if (start == 0 or not text[start - 1].isalnum()) and (
            ende == len(text) or not text[ende].isalnum()
        ):
            return True
        start = text.find(gesucht, start + 1)
    return False


def _eigene_nummer(a: Abrechnung, t: Transaktion) -> bool:
    return _nennt(_text(t), a.nummer)


def _fremd(lauf: _Lauf, a: Abrechnung, t: Transaktion) -> bool:
    """Regel 2: Der Umsatz nennt die Nummer einer anderen bekannten Abrechnung
    desselben Marktplatzes und nicht die eigene — er gehört zu jener Auszahlung."""
    schluessel = (t.id, a.marktplatz)
    if schluessel not in lauf.genannt:
        text = _text(t)
        lauf.genannt[schluessel] = {
            n
            for n in lauf.nummern.get(a.marktplatz, set())
            if len(n) >= _MINDESTLAENGE and n.upper() in text and _nennt(text, n)
        }
    return bool(lauf.genannt[schluessel] - {a.nummer}) and not _eigene_nummer(a, t)


def _andere_nummern(a: Abrechnung, t: Transaktion) -> list[str]:
    """Regel 4: Zahlen im Verwendungszweck mit der Form der eigenen Nummer (nur
    Ziffern, gleiche Länge, mindestens ``_MINDESTLAENGE``, dieselben ``_ANFANG``
    ersten Ziffern — die Nummern eines Marktplatzes laufen fort), nicht hinter einer
    Kunden-, Mandats-, Konto- oder Rechnungsangabe (``_REFERENZEN``), wenn der Umsatz
    die eigene nicht nennt — die Auszahlungsnummer einer Abrechnung, die accounti
    noch nicht kennt. Eine Referenz der Bank mit anderem Anfang (EREF 4711000815
    neben 6009990001) oder eine Kundennummer zählt nicht (Nachprüfung 5 E, M4). Leer
    bei Nummern anderer Form (PayPal-Zeitraum, Shopify ohne ID)."""
    nummer = a.nummer
    if not (
        len(nummer) >= _MINDESTLAENGE and nummer.isascii() and nummer.isdigit()
    ) or _eigene_nummer(a, t):
        return []
    text = _text(t)
    return [
        z.group()
        for z in _ZIFFERN.finditer(text)
        if len(z.group()) == len(nummer)
        and z.group()[:_ANFANG] == nummer[:_ANFANG]
        and (z.start() == 0 or not text[z.start() - 1].isalnum())
        and (z.end() == len(text) or not text[z.end()].isalnum())
        and not _bezeichnet(text[: z.start()])
    ]


def _bezeichnet(davor: str) -> bool:
    """Steht vor der Zahl eine Kunden-, Mandats-, Konto- oder Rechnungsangabe (``KD``,
    ``Kunden-Nr.``, ``MREF``, ``IBAN`` …)?"""
    woerter = _WORT.findall(davor)
    if len(woerter) > 1 and woerter[-1] in _NR:
        woerter = woerter[:-1]
    return bool(woerter) and woerter[-1] in _REFERENZEN


def _umsaetze(
    lauf: _Lauf, a: Abrechnung, p: Marktplatzposten, erwartet: Decimal
) -> list[Transaktion]:
    """Regeln 1–3: die Bankumsätze, unter denen Treffer und Befund des Postens
    gesucht werden — im Fenster, in Richtung der Auszahlung, keinem Posten
    zugeordnet, nicht fremd; nennt einer die eigene Nummer, nur die eigenen."""
    von, bis = _fenster(lauf, p)
    umsaetze = [
        t
        for t in lauf.bankumsaetze
        if t.id not in lauf.benutzt
        and t.id not in lauf.zugeordnet
        and von <= t.datum <= bis
        and (t.betrag > 0) == (erwartet > 0)
        and t.id not in lauf.ausgeschlossen.get(p.id, ())
        and not _fremd(lauf, a, t)
    ]
    return [t for t in umsaetze if _eigene_nummer(a, t)] or umsaetze


def _eingrenzen(
    kandidaten: list[Transaktion], *merkmale: Callable[[Transaktion], bool]
) -> list[Transaktion]:
    """Grenzt mehrere Kandidaten Merkmal für Merkmal ein; ein Merkmal, das keiner
    hat, grenzt nichts ein — bleiben mehrere, wird nicht geraten."""
    for merkmal in merkmale:
        if len(kandidaten) <= 1:
            break
        kandidaten = [t for t in kandidaten if merkmal(t)] or kandidaten
    return kandidaten


def _gegenkonto(kontext: Kontext, a: Abrechnung) -> str:
    """Gegenkonto der Bankbuchung: Verrechnungskonto, bei PayPal Geldtransit."""
    e = kontext.einstellungen
    if a.marktplatz == "paypal":
        return e.geldtransit_konto
    return e.marktplatz(a.marktplatz).verrechnungskonto


def _umbuchung(
    lauf: _Lauf, a: Abrechnung, umsaetze: list[Transaktion], ident: str
) -> str:
    """Der korrigiere-Befehl, der den Umsatz zur Geldbewegung auf das Gegenkonto
    der Abrechnung macht — wie ``_buche`` (Auszahlung: Bank an Gegenkonto)."""
    banken = {t.sachkonto or lauf.kontext.buchhaltung.bank_konto for t in umsaetze}
    bank = banken.pop() if len(banken) == 1 else "<Bankkonto>"
    gegen = _gegenkonto(lauf.kontext, a)
    soll, haben = (bank, gegen) if umsaetze[0].betrag > 0 else (gegen, bank)
    return f"accounti korrigiere {ident} --soll {soll} --haben {haben} --ohne-steuer"


def _buchungen(lauf: _Lauf, t: Transaktion) -> list[Buchungssatz]:
    """Was am Umsatz gilt (ohne Storno-Paare), je Lauf einmal gelesen."""
    if t.id not in lauf.buchungen:
        lauf.buchungen[t.id] = buchungen_zur_transaktion(lauf.session, t.id)
    return lauf.buchungen[t.id]


def _nur_geldbewegung(lauf: _Lauf, t: Transaktion) -> bool:
    """Der Umsatz ist nur zwischen Bank, Verrechnungs-, Geldtransit- und
    Kursdifferenzkonten gebucht, ohne Umsatzsteuer — eine Geldbewegung, kein Erlös
    (accountis eigene Bankbuchung, die Korrektur nach „anderweitig gebucht“)."""
    bank = t.sachkonto or lauf.kontext.buchhaltung.bank_konto
    konten = lauf.geldkonten | {bank}
    buchungen = _buchungen(lauf, t)
    return bool(buchungen) and all(
        {b.soll_konto, b.haben_konto} <= konten
        and not (b.steuer_schluessel is not None and b.steuer_betrag)
        for b in buchungen
    )


def _vorgebucht(lauf: _Lauf, a: Abrechnung, t: Transaktion) -> Decimal | None:
    """Steht der gebuchte, keinem Posten zugeordnete Umsatz als Geldbewegung schon
    auf dem Gegenkonto der Abrechnung: der Betrag dort (Haben positiv) — sonst
    ``None``."""
    if (
        t.id not in lauf.gebucht
        or t.id in lauf.zugeordnet
        or not _nur_geldbewegung(lauf, t)
    ):
        return None
    gegen = _gegenkonto(lauf.kontext, a)
    summe = sum(
        (
            b.betrag_netto if b.haben_konto == gegen else -b.betrag_netto
            for b in _buchungen(lauf, t)
            if gegen in (b.soll_konto, b.haben_konto) and b.soll_konto != b.haben_konto
        ),
        Decimal(0),
    )
    return summe or None


def _in_toleranz(lauf: _Lauf, betrag: Decimal, erwartet: Decimal) -> bool:
    """Fremdwährung: Bankbetrag höchstens ``auszahlung_toleranz_prozent`` neben der
    umgerechneten Auszahlung, gleiches Vorzeichen."""
    prozent = lauf.kontext.einstellungen.auszahlung_toleranz_prozent
    return (betrag > 0) == (erwartet > 0) and abs(betrag - erwartet) * 100 <= abs(
        erwartet
    ) * prozent


def _passt(lauf: _Lauf, a: Abrechnung, t: Transaktion, erwartet: Decimal) -> bool:
    """Exakt der erwartete Betrag — in Fremdwährung auch in der Toleranz."""
    return t.betrag == erwartet or (
        a.waehrung != "EUR" and _in_toleranz(lauf, t.betrag, erwartet)
    )


def _kandidaten(
    lauf: _Lauf, a: Abrechnung, p: Marktplatzposten, erwartet: Decimal
) -> list[Transaktion]:
    """Regel 5: unter ``_umsaetze`` die offenen — außer mit einer anderen Nummer
    (Regel 4) — oder die schon als Geldbewegung auf dem Gegenkonto stehenden
    (``_vorgebucht``) mit exakt dem erwarteten Betrag, bei Fremdwährung ohne solchen
    die mit Stichwort oder Nummer in der Toleranz. Mehrere grenzen Stichwort und
    eigene Nummer ein."""
    frei = [
        t
        for t in _umsaetze(lauf, a, p, erwartet)
        if (
            (t.id in lauf.offen_ids and not _andere_nummern(a, t))
            # Betrag zuerst: die Buchungen am Umsatz nur lesen, wo er passen kann
            or (_passt(lauf, a, t, erwartet) and _vorgebucht(lauf, a, t) is not None)
        )
    ]
    kandidaten = _eingrenzen(
        [t for t in frei if t.betrag == erwartet],
        lambda t: _erkennbar(lauf, a, t),
        lambda t: _eigene_nummer(a, t),
    )
    if not kandidaten and a.waehrung != "EUR":
        kandidaten = _eingrenzen(
            [
                t
                for t in frei
                if _erkennbar(lauf, a, t) and _in_toleranz(lauf, t.betrag, erwartet)
            ],
            lambda t: _eigene_nummer(a, t),
        )
    return kandidaten


def _zuordnen(
    lauf: _Lauf,
    a: Abrechnung,
    p: Marktplatzposten,
    t: Transaktion,
    erwartet: Decimal,
    von_hand: bool = False,
) -> Abgleich:
    """Eindeutiger Treffer: Befunde zu diesem Posten aus früheren Läufen erledigen
    sich; eine Kursdifferenz (Fremdwährung) steht als Hinweis an der Abrechnung.
    Steht der Umsatz schon auf dem Gegenkonto (``_vorgebucht``), wird nur noch die
    Kursdifferenz gebucht, nicht die Bank ein zweites Mal. Nennt der Umsatz die
    Nummer nicht, ist die Zuordnung geraten — das sagt ein Hinweis (``OHNE_NUMMER``),
    außer sie ist ``von_hand``."""
    vorgebucht = _vorgebucht(lauf, a, t)
    erledigt = [
        b
        for b in a.offene_befunde
        if b.code in ABGLEICHSBEFUNDE | {OHNE_NUMMER} and b.posten_nr == p.nr
    ]
    for b in erledigt:
        b.erledigt = True
    erledige_befunde(lauf.session, [b.id for b in erledigt])
    lauf.benutzt.add(t.id)
    setze_bank_transaktion(lauf.session, p.id, t.id)
    p.bank_transaktion_id = t.id
    a.status = status_von(a)
    _buche(lauf.session, lauf.kontext, a, t, erwartet, vorgebucht=vorgebucht)
    befund = None
    if t.betrag != erwartet:
        e = lauf.kontext.einstellungen
        differenz = t.betrag - erwartet
        konto = e.kursdifferenz_ertrag if differenz > 0 else e.kursdifferenz_aufwand
        befund = Befund(
            code="kursdifferenz",
            schweregrad=Schweregrad.HINWEIS,
            text=(
                f"{ANZEIGE.get(a.marktplatz, a.marktplatz)} {a.nummer}: Bank "
                f"{eur_text(t.betrag)} € ≠ Abrechnung {eur_text(erwartet)} € "
                f"({a.waehrung}, Kurs {a.kurs}) — Differenz {eur_text(differenz)} € "
                f"als Kursdifferenz auf {konto} gebucht"
            ),
            posten_nr=p.nr,
        )
        ergaenze_befunde(lauf.session, a.id, [befund])
        a.befunde.append(befund)
    if not von_hand and _nummer_wort(a) and not _eigene_nummer(a, t):
        markt = ANZEIGE.get(a.marktplatz, a.marktplatz)
        ident = str(t.id)[:8]
        hinweis = Befund(
            code=OHNE_NUMMER,
            schweregrad=Schweregrad.HINWEIS,
            text=(
                f"{markt} {a.nummer}: zugeordnet nach Betrag und Stichwort — der "
                f"Bankumsatz vom {t.datum:%d.%m.%Y} ({ident}) nennt {a.nummer} nicht. "
                "Gehört er zu einer anderen Abrechnung: accounti marktplatz zuordnen "
                f"<Nummer> {ident}"
            ),
            posten_nr=p.nr,
        )
        ergaenze_befunde(lauf.session, a.id, [hinweis])
        a.befunde.append(hinweis)
    return Abgleich(a, p, t, befund)


def _nummer_wort(a: Abrechnung) -> bool:
    """Kann ein Verwendungszweck die Nummer als Wort nennen (Regel 3)? Nicht der
    Zeitraum einer PayPal-Datei, keine zu kurze Nummer."""
    return (
        len(a.nummer) >= _MINDESTLAENGE
        and _WORT.fullmatch(a.nummer.upper()) is not None
    )


def _befund(
    lauf: _Lauf, a: Abrechnung, p: Marktplatzposten, erwartet: Decimal
) -> Abgleich:
    """Regel 6: kein eindeutiger Treffer — mehrdeutig (auch: derselbe Umsatz einziger
    Kandidat mehrerer Abrechnungen), abweichend, anderweitig gebucht, umgebucht, eine
    andere Nummer — oder einfach noch nicht auf der Bank."""
    markt = ANZEIGE.get(a.marktplatz, a.marktplatz)
    kandidaten = _kandidaten(lauf, a, p, erwartet)
    if kandidaten:
        return Abgleich(
            a,
            p,
            befund=_mehrdeutig(lauf, a, p, erwartet, kandidaten),
            umsaetze=kandidaten,
        )
    # nur eigene, sonst keine fremden (Regeln 2, 3)
    alle = _umsaetze(lauf, a, p, erwartet)
    umsaetze = [t for t in alle if _erkennbar(lauf, a, t)]
    # Fremdwährung: dieselbe Toleranz wie beim Treffer — die Bank rechnet mit ihrem
    # eigenen Kurs, exakt gleich ist der gebuchte Umsatz fast nie (sonst stünde der
    # Erlös still doppelt in der Voranmeldung). Ein zugeordneter oder fremder Umsatz
    # (``_umsaetze``) und eine Geldbewegung sind nicht „schon gebucht“ — sonst träfe
    # die Toleranz den Umsatz der vorigen Auszahlung (Nachprüfung 2 E, M1; 3 E, M2);
    # nennt einer die eigene Nummer, nur er (4 E, M3). Mit exakt dem erwarteten Betrag
    # auch ohne Stichwort — wie beim Treffer (Regel 5); sonst schwieg die Voranmeldung,
    # wo kein Stichwort eingestellt ist (Nachprüfung 5 E, Simulation)
    gebucht = [
        t
        for t in alle
        if t.id in lauf.gebucht and (_erkennbar(lauf, a, t) or t.betrag == erwartet)
    ]
    passend = [t for t in gebucht if _passt(lauf, a, t, erwartet)]
    # mehrere: die eigene Nummer, keine andere, dann der exakte Betrag (in
    # Fremdwährung Zufall, die Nummer nicht; in Euro sind ohnehin alle exakt) —
    # sonst alle nennen
    merkmale: tuple[Callable[[Transaktion], bool], ...] = (
        lambda t: _eigene_nummer(a, t),
        lambda t: not _andere_nummern(a, t),
        lambda t: t.betrag == erwartet,
    )
    schon = _eingrenzen(
        [t for t in passend if not _nur_geldbewegung(lauf, t)], *merkmale
    )
    if schon:
        return Abgleich(a, p, befund=_schon_gebucht(lauf, a, p, schon), umsaetze=schon)
    # der eigene (mit der Nummer) als Erlös gebucht, aber außerhalb der Toleranz:
    # die Erlöse sind trotzdem doppelt (Nachprüfung 5 E, N2)
    abweichend = [
        t
        for t in gebucht
        if _eigene_nummer(a, t)
        and not _passt(lauf, a, t, erwartet)
        and not _nur_geldbewegung(lauf, t)
    ]
    if abweichend:
        return Abgleich(
            a,
            p,
            befund=_schon_gebucht(lauf, a, p, abweichend, erwartet),
            umsaetze=abweichend,
        )
    # nach „schon gebucht“ (doppelter Erlös geht vor): offen in anderer Höhe — oder
    # der eigene (mit der Nummer), der als Geldbewegung
    # schon auf dem Gegenkonto steht, aber außerhalb der Toleranz (Nachprüfung 5 E,
    # N2: falscher Kurs, Teilbetrag)
    anders = [
        t
        for t in umsaetze
        if (
            t.id in lauf.offen_ids
            and t.betrag != erwartet
            and not _andere_nummern(a, t)
        )
        or (
            _eigene_nummer(a, t)
            and not _passt(lauf, a, t, erwartet)
            and _vorgebucht(lauf, a, t) is not None
        )
    ]
    if anders:
        (t, *_) = _eingrenzen(anders, lambda t: _eigene_nummer(a, t))
        vorgebucht = (
            f" (als Geldbewegung auf {_gegenkonto(lauf.kontext, a)} gebucht)"
            if t.id not in lauf.offen_ids
            else ""
        )
        return Abgleich(
            a,
            p,
            befund=Befund(
                code="auszahlung_abweichung",
                schweregrad=Schweregrad.FEHLER,
                text=(
                    f"{markt} {a.nummer}: Bankumsatz vom {t.datum:%d.%m.%Y} über "
                    f"{eur_text(t.betrag)} €{vorgebucht} ≠ Auszahlung laut Abrechnung "
                    f"{eur_text(erwartet)} € — nicht gebucht, Differenz klären "
                    "(Kurs der Abrechnung, Teilbetrag)"
                ),
                posten_nr=p.nr,
            ),
            umsaetze=[t],
        )
    # eine Geldbewegung, aber auf einem anderen Konto (z. B. Geldtransit statt
    # Verrechnungskonto): kein doppelter Erlös, doch die Auszahlung bliebe still
    # offen und das Verrechnungskonto mit Saldo (Nachprüfung 3 E, L-b)
    umgebucht = _eingrenzen(
        [
            t
            for t in passend
            if _erkennbar(lauf, a, t)
            and _nur_geldbewegung(lauf, t)
            and _vorgebucht(lauf, a, t) is None
        ],
        *merkmale,
    )
    if umgebucht:
        return Abgleich(
            a, p, befund=_umgebucht(lauf, a, p, umgebucht), umsaetze=umgebucht
        )
    # Regel 4: passt nur ein Umsatz mit einer anderen Nummer, wird er nicht
    # zugeordnet — er bliebe sonst der falschen Abrechnung, und ihre eigene fände
    # später ihren Umsatz nicht mehr (Nachprüfung 4 E, M3)
    andere = [
        t
        for t in umsaetze
        if t.id in lauf.offen_ids
        and _andere_nummern(a, t)
        and _passt(lauf, a, t, erwartet)
    ]
    if andere:
        return Abgleich(a, p, befund=_andere_nummer(a, p, andere), umsaetze=andere)
    return Abgleich(a, p)


def _mehrdeutig(
    lauf: _Lauf,
    a: Abrechnung,
    p: Marktplatzposten,
    erwartet: Decimal,
    kandidaten: list[Transaktion],
) -> Befund:
    """WARNUNG ``auszahlung_mehrdeutig``: mehrere Umsätze passen — oder ein Umsatz
    ist der einzige Kandidat auch der Auszahlung einer anderen Abrechnung (Regel 5).
    Es wird nicht geraten; der Befund nennt je Umsatz den Befehl."""
    markt = ANZEIGE.get(a.marktplatz, a.marktplatz)
    andere = lauf.umstritten.get(p.id, [])
    if len(kandidaten) == 1 and andere:
        (t,) = kandidaten
        wer = ", ".join(
            f"{ANZEIGE.get(x.marktplatz, x.marktplatz)} {x.nummer}" for x in andere
        )
        text = (
            f"{markt} {a.nummer}: Der Bankumsatz vom {t.datum:%d.%m.%Y} über "
            f"{eur_text(t.betrag)} € ({str(t.id)[:8]}) passt auch zur Auszahlung von "
            f"{wer}, und kein Verwendungszweck nennt die Nummer — es wird nicht "
            f"geraten. Ist er diese Auszahlung: accounti marktplatz zuordnen "
            f"{a.nummer} {str(t.id)[:8]}"
        )
    else:
        liste = "; ".join(
            f"vom {t.datum:%d.%m.%Y}: accounti marktplatz zuordnen {a.nummer} "
            f"{str(t.id)[:8]}"
            for t in kandidaten
        )
        text = (
            f"{markt} {a.nummer}: {len(kandidaten)} Bankumsätze über "
            f"{eur_text(erwartet)} € passen — es wird nicht geraten, den richtigen "
            f"zuordnen ({liste})"
        )
    return Befund(
        code="auszahlung_mehrdeutig",
        schweregrad=Schweregrad.WARNUNG,
        text=text,
        posten_nr=p.nr,
    )


def _nennende(lauf: _Lauf, a: Abrechnung) -> list[Transaktion]:
    """Umsätze, die die eigene Nummer nennen — über ein Verzeichnis der Wörter im
    Verwendungszweck, einmal je Lauf gebaut (Regel 8 prüft jede frühere
    Zuordnung). Eine Nummer, die kein Wort aus Buchstaben und Ziffern ist
    (PayPal-Zeitraum), findet es nicht — kein Verwendungszweck nennt sie so."""
    if lauf.woerter is None:
        lauf.woerter = {}
        for t in lauf.bankumsaetze:
            for wort in set(_WORT.findall(_text(t))):
                if len(wort) >= _MINDESTLAENGE:
                    lauf.woerter.setdefault(wort, []).append(t)
    return [t for t in lauf.woerter.get(a.nummer.upper(), []) if _eigene_nummer(a, t)]


def _zweifel(
    lauf: _Lauf, a: Abrechnung, p: Marktplatzposten
) -> tuple[Befund, list[Transaktion]] | None:
    """Regel 8: Die Auszahlung ist einem Umsatz zugeordnet, der ihre Nummer nicht
    nennt (Stichwort und Betrag — damals nannte sie keiner).

    - Steht jetzt im Fenster einer mit der Nummer, als Erlös gebucht, sind die
      Erlöse doppelt: Fehler „schon gebucht“, die Voranmeldung seines Monats warnt.
    - Ist er offen oder als Geldbewegung auf dem Gegenkonto (nach der Korrektur),
      ist das ``auszahlung_zweifel`` (Warnung).
    - Nennt der zugeordnete Umsatz die Nummer einer inzwischen bekannten anderen
      Abrechnung desselben Marktplatzes (Regel 2 kam zu spät), ebenfalls.

    Die Zuordnung bleibt — der Befund nennt ``accounti marktplatz zuordnen`` (Regel
    9), das sie löst. Eine Zuordnung von Hand bezweifelt nur der doppelte Erlös."""
    erwartet = _erwartet(a, p)
    if erwartet is None or len(a.nummer) < _MINDESTLAENGE:
        return None
    zugeordnet = next(
        (t for t in lauf.bankumsaetze if t.id == p.bank_transaktion_id), None
    )
    if zugeordnet is None or _eigene_nummer(a, zugeordnet):
        return None
    markt = ANZEIGE.get(a.marktplatz, a.marktplatz)
    ident = str(zugeordnet.id)[:8]
    von, bis = _fenster(lauf, p)
    nennende = [
        t
        for t in _nennende(lauf, a)
        if von <= t.datum <= bis
        and t.id not in lauf.zugeordnet
        and t.id not in lauf.benutzt
        and t.id not in lauf.ausgeschlossen.get(p.id, ())
        and _passt(lauf, a, t, erwartet)
    ]
    eigene = [
        t for t in nennende if t.id in lauf.gebucht and not _nur_geldbewegung(lauf, t)
    ]
    if eigene:
        befund = _schon_gebucht(lauf, a, p, eigene)
        danach = (
            f"Ist er diese Auszahlung: nach der Korrektur accounti marktplatz "
            f"zuordnen {a.nummer} {str(eigene[0].id)[:8]} — das löst die Zuordnung, "
            "der andere wird frei"
            if len(eigene) == 1
            else "Nach der Korrektur den richtigen mit accounti marktplatz zuordnen "
            f"{a.nummer} <Umsatz> zuordnen — das löst die Zuordnung"
        )
        text = (
            f"{befund.text}. Zugeordnet ist aber der Bankumsatz vom "
            f"{zugeordnet.datum:%d.%m.%Y} ({ident}), der {a.nummer} nicht nennt — "
            f"einer von beiden gehört nicht zu dieser Auszahlung. {danach}"
        )
        return befund.model_copy(update={"text": text}), eigene
    if p.id in lauf.von_hand:
        return None
    frei = [
        t
        for t in nennende
        if t.id in lauf.offen_ids or _vorgebucht(lauf, a, t) is not None
    ]
    if frei:
        (t, *_) = _eingrenzen(frei, lambda t: t.betrag == erwartet)
        text = (
            f"{markt} {a.nummer}: Der Bankumsatz vom {t.datum:%d.%m.%Y} über "
            f"{eur_text(t.betrag)} € ({str(t.id)[:8]}) nennt {a.nummer} und ist "
            f"keiner Auszahlung zugeordnet — zugeordnet ist der vom "
            f"{zugeordnet.datum:%d.%m.%Y} ({ident}), der {a.nummer} nicht nennt "
            "(damals nannte keiner die Nummer). Ist der mit der Nummer diese "
            f"Auszahlung: accounti marktplatz zuordnen {a.nummer} {str(t.id)[:8]} — "
            "das löst die Zuordnung, der andere wird frei"
        )
        return _zweifel_befund(p, text), frei
    if _fremd(lauf, a, zugeordnet):
        andere = sorted(lauf.genannt[(zugeordnet.id, a.marktplatz)] - {a.nummer})
        text = (
            f"{markt} {a.nummer}: Der zugeordnete Bankumsatz vom "
            f"{zugeordnet.datum:%d.%m.%Y} ({ident}) nennt {', '.join(andere)}, nicht "
            f"{a.nummer} — zugeordnet, bevor jene Abrechnung bekannt war. Gehört er "
            f"zu ihr: accounti marktplatz zuordnen {andere[0]} {ident} — das löst "
            "diese Zuordnung"
        )
        return _zweifel_befund(p, text), []
    return None


def _zweifel_befund(p: Marktplatzposten, text: str) -> Befund:
    return Befund(
        code="auszahlung_zweifel",
        schweregrad=Schweregrad.WARNUNG,
        text=text,
        posten_nr=p.nr,
    )


def _liste(lauf: _Lauf, umsaetze: list[Transaktion]) -> tuple[str, str]:
    """(„vom 30.09.2026: eea596bb; vom …“, ID für den korrigiere-Befehl)."""
    teile, erste = [], "<ID>"
    for t in umsaetze:
        ids = [str(b.id)[:8] for b in _buchungen(lauf, t)]
        teile.append(f"vom {t.datum:%d.%m.%Y}: {', '.join(ids) or '?'}")
        if len(umsaetze) == 1 and ids:
            erste = ids[0]
    return "; ".join(teile), erste


def _schon_gebucht(
    lauf: _Lauf,
    a: Abrechnung,
    p: Marktplatzposten,
    schon: list[Transaktion],
    abweichend: Decimal | None = None,
) -> Befund:
    """FEHLER ``auszahlung_anderweitig_gebucht``: ein Umsatz — oder, nicht
    entscheidbar, mehrere — schon als Erlös gebucht; ``bankdaten`` liest die Tage.
    ``abweichend``: die erwartete Auszahlung, wenn der Umsatz die eigene Nummer
    nennt, sein Betrag aber außerhalb der Toleranz liegt (Nachprüfung 5 E, N2)."""
    markt = ANZEIGE.get(a.marktplatz, a.marktplatz)
    geldbewegung = "(die Auszahlung ist eine Geldbewegung ohne Umsatzsteuer)"
    if len(schon) == 1:
        (t,) = schon
        ids = [str(b.id)[:8] for b in _buchungen(lauf, t)]
        befehl = _umbuchung(lauf, a, schon, ids[0] if ids else "<ID>")
        # Regel 4: nennt er eine andere Nummer, gehört er wohl zu einer noch nicht
        # importierten Abrechnung — dann erledigt deren Import den Befund
        andere = _andere_nummern(a, t)
        if abweichend is not None:
            vorbehalt = (
                f" Er nennt {a.nummer}, sein Betrag {eur_text(t.betrag)} € weicht "
                f"aber von der Auszahlung {eur_text(abweichend)} € ab (außerhalb "
                "der Toleranz: Kurs der Abrechnung oder Teilbetrag klären). "
                "Korrigieren"
            )
        elif andere:
            vorbehalt = (
                f" Er nennt {', '.join(andere)}, nicht {a.nummer} — gehört er zu einer "
                "noch nicht importierten Abrechnung, erst diese importieren, dann "
                "erledigt sich der Befund. Sonst korrigieren"
            )
        else:
            vorbehalt = " Korrigieren"
        # danach gleicht der Abgleich ihn ab (Regel 5); gehört er zu einer anderen
        # Abrechnung, ordnet ihn der Mensch dort zu (Regel 9)
        zuordnen = (
            ""
            if _eigene_nummer(a, t)
            else "; danach gleicht der Abgleich ihn hier ab — gehört er zu einer "
            "anderen Abrechnung, dort mit accounti marktplatz zuordnen <Nummer> "
            f"{str(t.id)[:8]}"
        )
        text = (
            f"{markt} {a.nummer}: {_SCHON_GEBUCHT.format(tag=t.datum)} "
            f"({', '.join(ids)}) — Erlöse wären doppelt.{vorbehalt} mit {befehl} "
            f"{geldbewegung}{zuordnen}"
        )
    else:
        liste, ident = _liste(lauf, schon)
        text = (
            f"{markt} {a.nummer}: {len(schon)} {_SCHON_GEBUCHT_MEHRERE} ({liste}) — "
            "einer davon ist die Auszahlung, ihre Erlöse wären doppelt; welcher, "
            "nennt kein Verwendungszweck, es wird nicht geraten. Den richtigen "
            f"korrigieren mit {_umbuchung(lauf, a, schon, ident)} {geldbewegung}; "
            "gehört einer zu einer anderen Abrechnung, danach dort mit accounti "
            "marktplatz zuordnen <Nummer> <Umsatz>"
        )
    return Befund(
        code="auszahlung_anderweitig_gebucht",
        schweregrad=Schweregrad.FEHLER,
        text=text,
        posten_nr=p.nr,
    )


def _umgebucht(
    lauf: _Lauf, a: Abrechnung, p: Marktplatzposten, umsaetze: list[Transaktion]
) -> Befund:
    """WARNUNG ``auszahlung_umgebucht``: die Auszahlung ist als Geldbewegung gebucht,
    aber nicht auf dem Gegenkonto der Abrechnung."""
    markt = ANZEIGE.get(a.marktplatz, a.marktplatz)
    gegen = _gegenkonto(lauf.kontext, a)
    banken = {t.sachkonto or lauf.kontext.buchhaltung.bank_konto for t in umsaetze}
    konten = sorted(
        {
            k
            for t in umsaetze
            for b in _buchungen(lauf, t)
            for k in (b.soll_konto, b.haben_konto)
        }
        - banken
    )
    liste, ident = _liste(lauf, umsaetze)
    wer = (
        f"Der Bankumsatz ({liste}) ist"
        if len(umsaetze) == 1
        else f"{len(umsaetze)} Bankumsätze ({liste}) sind"
    )
    return Befund(
        code="auszahlung_umgebucht",
        schweregrad=Schweregrad.WARNUNG,
        text=(
            f"{markt} {a.nummer}: {wer} als Geldbewegung auf "
            f"{', '.join(konten) or '?'} gebucht, nicht auf {gegen} — die Auszahlung "
            f"bleibt offen, {gegen} behält den Saldo. Umbuchen mit "
            f"{_umbuchung(lauf, a, umsaetze, ident)}"
        ),
        posten_nr=p.nr,
    )


def _andere_nummer(
    a: Abrechnung, p: Marktplatzposten, umsaetze: list[Transaktion]
) -> Befund:
    """WARNUNG ``auszahlung_andere_nummer`` (Regel 4): passt nur ein Umsatz, der eine
    andere Nummer derselben Form nennt — wohl die Auszahlung einer Abrechnung, die
    noch nicht importiert ist. Ist die Zahl doch eine Referenz der Bank, ordnet ihn
    ``accounti marktplatz zuordnen`` zu (Regel 9)."""
    markt = ANZEIGE.get(a.marktplatz, a.marktplatz)
    teile = "; ".join(
        f"vom {t.datum:%d.%m.%Y} über {eur_text(t.betrag)} € ({str(t.id)[:8]}, "
        f"„{', '.join(_andere_nummern(a, t))}“)"
        for t in umsaetze
    )
    befehle = " bzw. ".join(
        f"accounti marktplatz zuordnen {a.nummer} {str(t.id)[:8]}" for t in umsaetze
    )
    wer = "Der Bankumsatz" if len(umsaetze) == 1 else f"{len(umsaetze)} Bankumsätze"
    return Befund(
        code="auszahlung_andere_nummer",
        schweregrad=Schweregrad.WARNUNG,
        text=(
            f"{markt} {a.nummer}: {wer} {teile} passt im Betrag, nennt aber eine "
            f"andere Nummer statt {a.nummer} — wohl die Auszahlung einer noch nicht "
            "importierten Abrechnung, nicht zugeordnet. Mit deren Import erledigt "
            "sich das; ist er doch diese Auszahlung (die Zahl ist etwa eine Referenz "
            f"der Bank): {befehle}"
        ),
        posten_nr=p.nr,
    )


def _buche(
    session: Session,
    kontext: Kontext,
    a: Abrechnung,
    t: Transaktion,
    erwartet: Decimal | None = None,
    vorgebucht: Decimal | None = None,
) -> None:
    """Bank an Verrechnungskonto über die Auszahlung laut Abrechnung; weicht der
    Bankbetrag ab (Fremdwährung), geht die Differenz auf ein Kursdifferenzkonto —
    das Verrechnungskonto ist danach ausgeglichen, die Bank hat ihren Betrag.

    ``vorgebucht``: der Umsatz steht schon mit diesem Betrag auf dem Gegenkonto (die
    Korrektur nach „anderweitig gebucht“ bucht den Bankbetrag) — die Bank ist
    gebucht; was das Gegenkonto mehr oder weniger bekam als laut Abrechnung, ist
    Kursdifferenz und wird umgebucht (ohne Bank, ohne Umsatz)."""
    e = kontext.einstellungen
    bank = t.sachkonto or kontext.buchhaltung.bank_konto
    gegen = _gegenkonto(kontext, a)
    pruefen = status_von(a) is AbrechnungStatus.ABWEICHUNG
    markt = ANZEIGE.get(a.marktplatz, a.marktplatz)
    art = "Auszahlung" if t.betrag > 0 else "Einzahlung"
    erwartet = t.betrag if erwartet is None else erwartet
    # (Betrag, Konto, Text, Seite): positiver Betrag — die Seite (Bank: Geld kommt
    # auf die Bank; Gegenkonto: es bekam zu viel) im Soll
    teile: list[tuple[Decimal, str, str, str]] = []
    if vorgebucht is not None:
        rest = vorgebucht - erwartet  # Haben-Überschuss auf dem Gegenkonto
        if rest:
            konto = e.kursdifferenz_ertrag if rest > 0 else e.kursdifferenz_aufwand
            teile.append((rest, konto, f"{markt} Kursdifferenz {a.nummer}", gegen))
    else:
        differenz = t.betrag - erwartet
        teile.append((erwartet, gegen, f"{markt} {art} {a.nummer}", bank))
        if differenz:
            konto = e.kursdifferenz_ertrag if differenz > 0 else e.kursdifferenz_aufwand
            teile.append((differenz, konto, f"{markt} Kursdifferenz {a.nummer}", bank))
    for betrag, konto, text, seite in teile:
        soll, haben = (seite, konto) if betrag > 0 else (konto, seite)
        speichere_buchung(
            session,
            Buchungssatz(
                # die Umbuchung einer Kursdifferenz berührt die Bank nicht
                transaktion_id=t.id if seite == bank else None,
                beleg_id=a.beleg_id,
                datum=t.datum,
                soll_konto=soll,
                haben_konto=haben,
                betrag_netto=abs(betrag),
                buchungstext=text[:60],
                beleg_nummer=a.nummer[:36],
                status=BuchungStatus.ZUR_PRUEFUNG
                if pruefen
                else BuchungStatus.AUTO_GEBUCHT,
                confidence=0.5 if pruefen else 1.0,
            ),
        )
    session.flush()


# --- Regel 9: Zuordnung von Hand --------------------------------------------------


class ZuordnungError(ValueError):
    """Die Zuordnung von Hand ist so nicht möglich (nichts geändert)."""


@dataclass
class Handzuordnung:
    abrechnung: Abrechnung
    posten: Marktplatzposten
    transaktion: Transaktion | None  # zugeordnet; None: gelöst
    geloest: list[str] = field(default_factory=list)  # aufgehobene Zuordnungen
    warnungen: list[str] = field(default_factory=list)  # aus den Stornos
    abgleich: list[Abgleich] = field(default_factory=list)  # der Abgleich danach


def ordne_zu(
    session: Session,
    kontext: Kontext,
    nummer: str,
    umsatz: str | None,
    *,
    posten: int | None = None,
    von: str | None = None,
    datum: date | None = None,
) -> Handzuordnung:
    """Regel 9: ordnet der Auszahlung (Einzahlung) der Abrechnung ``nummer`` den
    Bankumsatz ``umsatz`` (Anfang seiner ID) ausdrücklich zu — der Ausweg, wo der
    Abgleich nicht entscheidet (eine Bankreferenz derselben Form, Regel 4; mehrdeutig;
    eine Zuordnung ohne Nummer, die Regel 8 bezweifelt). Ohne ``umsatz`` löst es die
    Zuordnung: der Umsatz gehört nicht zu dieser Auszahlung, der Abgleich nimmt ihn
    hier nicht wieder (Hinweis ``GELOEST``).

    Ist der Umsatz einer anderen Auszahlung zugeordnet oder die Auszahlung einem
    anderen Umsatz, wird diese Zuordnung zuerst gelöst: accountis Bankbuchung dazu
    (Bank an Verrechnungskonto, Kursdifferenz) wird storniert (``datum``: Storno-Tag,
    wenn ihr Zeitraum abgeschlossen ist), ein Vorschlag verworfen. Danach bucht
    accounti wie beim Treffer und gleicht alle offenen Auszahlungen neu ab — ein frei
    gewordener Umsatz findet so seine Abrechnung. Ein als Erlös gebuchter Umsatz wird
    nicht still umgebucht: erst ``accounti korrigiere`` (die Meldung nennt den
    Befehl). Betrag und Richtung müssen passen (Fremdwährung: in der Toleranz).

    Die Zuordnung steht im Journal (``auszahlung_zugeordnet`` bzw.
    ``auszahlung_geloest``, Person aus dem Journal-Kontext) und als Hinweis an der
    Abrechnung; die Stornos tragen ``von`` als Person. Bei einem Fehler nichts
    festschreiben (die Sitzung ist dann teilweise geändert)."""
    from accounti.abschluss.kontenrahmen import lade_kontenrahmen
    from accounti.pruefung.journal import schreibe
    from accounti.pruefung.person import aktuelle_person

    try:
        a = lade_abrechnung(session, nummer)
    except ValueError as fehler:
        raise ZuordnungError(str(fehler)) from fehler
    p = _auszahlungsposten(a, posten)
    markt = ANZEIGE.get(a.marktplatz, a.marktplatz)
    erwartet = _erwartet(a, p)
    if erwartet is None:
        raise ZuordnungError(
            f"{markt} {a.nummer}: die Auszahlung ist nicht gebucht (Fremdwährung ohne "
            "Kurs oder 0 €) — nichts zuzuordnen"
        )
    person = aktuelle_person(von)
    kr = lade_kontenrahmen(kontext.buchhaltung.kontenrahmen)
    ergebnis = Handzuordnung(a, p, None)
    vorher = p.bank_transaktion_id
    lauf = _neuer_lauf(session, kontext, lade_abrechnungen(session))

    if umsatz is None:
        if p.bank_transaktion_id is None:
            raise ZuordnungError(
                f"{markt} {a.nummer}: die Auszahlung ist keinem Bankumsatz zugeordnet "
                "— nichts zu lösen"
            )
        alt = _umsatz_mit_id(lauf, p.bank_transaktion_id)
        _loese_in(ergebnis, session, kontext, a, p, alt, person, datum, kr)
        ident = str(alt.id)[:8]
        _merke(
            session,
            a,
            Befund(
                code=GELOEST,
                schweregrad=Schweregrad.HINWEIS,
                text=(
                    f"{markt} {a.nummer}: Zuordnung des Bankumsatzes vom "
                    f"{alt.datum:%d.%m.%Y} über {eur_text(alt.betrag)} € ({ident}) "
                    f"von Hand gelöst ({person}) — der Abgleich nimmt ihn für diese "
                    f"Auszahlung nicht wieder; doch zuordnen mit accounti marktplatz "
                    f"zuordnen {a.nummer} {ident} [Umsatz {alt.id}]"
                ),
                posten_nr=p.nr,
            ),
        )
        vorgang, nachher = "auszahlung_geloest", None
    else:
        t = _finde_umsatz(lauf, umsatz)
        if p.bank_transaktion_id == t.id:
            raise ZuordnungError(
                f"{markt} {a.nummer}: der Bankumsatz {str(t.id)[:8]} ist dieser "
                "Auszahlung schon zugeordnet"
            )
        _pruefe_umsatz(lauf, a, t, erwartet)
        # erst lösen, was im Weg steht: der Umsatz bei einer anderen Auszahlung, die
        # Auszahlung bei einem anderen Umsatz
        for a2 in lade_abrechnungen(session):
            for p2 in a2.posten:
                if p2.bank_transaktion_id == t.id:
                    _loese_in(ergebnis, session, kontext, a2, p2, t, person, datum, kr)
        if p.bank_transaktion_id is not None:
            alt = _umsatz_mit_id(lauf, p.bank_transaktion_id)
            _loese_in(ergebnis, session, kontext, a, p, alt, person, datum, kr)
        # frisch: Buchungen, Zuordnungen und Befunde nach dem Lösen
        a = lade_abrechnung(session, str(a.id))
        p = next(x for x in a.posten if x.id == p.id)
        lauf = _neuer_lauf(session, kontext, lade_abrechnungen(session))
        _pruefe_buchungen(lauf, a, t)
        erledigt = [
            b
            for b in a.offene_befunde
            if b.posten_nr == p.nr
            and (
                b.code == VON_HAND
                or (b.code == GELOEST and f"[Umsatz {t.id}]" in b.text)
            )
        ]
        for b in erledigt:
            b.erledigt = True
        erledige_befunde(session, [b.id for b in erledigt])
        _zuordnen(lauf, a, p, t, erwartet, von_hand=True)
        ident = str(t.id)[:8]
        _merke(
            session,
            a,
            Befund(
                code=VON_HAND,
                schweregrad=Schweregrad.HINWEIS,
                text=(
                    f"{markt} {a.nummer}: Bankumsatz vom {t.datum:%d.%m.%Y} über "
                    f"{eur_text(t.betrag)} € ({ident}) von Hand zugeordnet ({person}) "
                    f"[Umsatz {t.id}]"
                ),
                posten_nr=p.nr,
            ),
        )
        ergebnis.transaktion = t
        vorgang, nachher = "auszahlung_zugeordnet", str(t.id)
    a.status = status_von(a)
    setze_abrechnungsstatus(session, a.id, a.status)
    schreibe(
        session,
        vorgang,
        "marktplatzposten",
        str(p.id),
        vorher={"abrechnung": a.nummer, "bank_transaktion_id": _str(vorher)},
        nachher={"abrechnung": a.nummer, "bank_transaktion_id": nachher},
        grund=f"{markt} {a.nummer}: Zuordnung von Hand",
    )
    ergebnis.abrechnung, ergebnis.posten = a, p
    ergebnis.abgleich = gleiche_auszahlungen_ab(session, kontext)
    return ergebnis


def _loese_in(
    ergebnis: Handzuordnung,
    session: Session,
    kontext: Kontext,
    a: Abrechnung,
    p: Marktplatzposten,
    t: Transaktion,
    person: str,
    datum: date | None,
    kr: Kontenrahmen,
) -> None:
    text, warnungen = _loese(session, kontext, a, p, t, person, datum, kr)
    ergebnis.geloest.append(text)
    ergebnis.warnungen.extend(warnungen)


def _str(wert: UUID | None) -> str | None:
    return str(wert) if wert is not None else None


def _merke(session: Session, a: Abrechnung, befund: Befund) -> None:
    ergaenze_befunde(session, a.id, [befund])
    a.befunde.append(befund)


def _auszahlungsposten(a: Abrechnung, nr: int | None) -> Marktplatzposten:
    """Die Aus- oder Einzahlung der Abrechnung — mit ``nr``, wenn sie mehrere hat."""
    markt = ANZEIGE.get(a.marktplatz, a.marktplatz)
    posten = [
        p
        for p in a.posten
        if p.art in (Postenart.AUSZAHLUNG, Postenart.EINZAHLUNG)
        and (p.betrag or p.betrag_eur)
        and (nr is None or p.nr == nr)
    ]
    if not posten:
        raise ZuordnungError(
            f"{markt} {a.nummer}: keine Aus- oder Einzahlung"
            + (f" in Zeile {nr}" if nr is not None else "")
        )
    if len(posten) > 1:
        zeilen = ", ".join(str(p.nr) for p in posten)
        raise ZuordnungError(
            f"{markt} {a.nummer}: mehrere Aus-/Einzahlungen (Zeilen {zeilen}) — mit "
            "--posten <Zeile> wählen"
        )
    return posten[0]


def _umsatz_mit_id(lauf: _Lauf, ident: UUID) -> Transaktion:
    for t in lauf.bankumsaetze:
        if t.id == ident:
            return t
    raise ZuordnungError(f"Bankumsatz {str(ident)[:8]} nicht gefunden")


def _finde_umsatz(lauf: _Lauf, anfang: str) -> Transaktion:
    """Bankumsatz über den Anfang seiner ID — nicht PayPal, nicht auf einem
    Verrechnungskonto (Regel 1)."""
    gesucht = anfang.strip().lower()
    treffer = [
        t for t in lauf.bankumsaetze if gesucht and str(t.id).startswith(gesucht)
    ]
    if not treffer:
        raise ZuordnungError(
            f"Kein Bankumsatz '{anfang}' (PayPal-Umsätze und Umsätze auf einem "
            "Verrechnungskonto sind keine Auszahlung auf die Bank)"
        )
    if len(treffer) > 1:
        raise ZuordnungError(
            f"'{anfang}' passt auf mehrere Bankumsätze — länger angeben"
        )
    return treffer[0]


def _pruefe_umsatz(
    lauf: _Lauf, a: Abrechnung, t: Transaktion, erwartet: Decimal
) -> None:
    """Richtung und Betrag (Fremdwährung: in der Toleranz) müssen passen."""
    markt = ANZEIGE.get(a.marktplatz, a.marktplatz)
    art = "Auszahlung" if erwartet > 0 else "Einzahlung"
    if (t.betrag > 0) != (erwartet > 0):
        raise ZuordnungError(
            f"{markt} {a.nummer}: der Bankumsatz {str(t.id)[:8]} über "
            f"{eur_text(t.betrag)} € hat die falsche Richtung für die {art} über "
            f"{eur_text(erwartet)} €"
        )
    if not _passt(lauf, a, t, erwartet):
        toleranz = (
            f" (außerhalb der Toleranz von "
            f"{lauf.kontext.einstellungen.auszahlung_toleranz_prozent} %)"
            if a.waehrung != "EUR"
            else ""
        )
        raise ZuordnungError(
            f"{markt} {a.nummer}: Bankumsatz {str(t.id)[:8]} über "
            f"{eur_text(t.betrag)} € ≠ {art} {eur_text(erwartet)} €{toleranz} — nicht "
            "zugeordnet; die Differenz klären (Kurs der Abrechnung, Teilbetrag)"
        )


def _pruefe_buchungen(lauf: _Lauf, a: Abrechnung, t: Transaktion) -> None:
    """Ein gebuchter Umsatz muss als Geldbewegung auf dem Gegenkonto stehen — ein
    Erlös oder eine Geldbewegung auf einem anderen Konto wird erst korrigiert."""
    if t.id not in lauf.gebucht or t.id in lauf.zugeordnet:
        return
    markt = ANZEIGE.get(a.marktplatz, a.marktplatz)
    ids = [str(b.id)[:8] for b in _buchungen(lauf, t)]
    befehl = _umbuchung(lauf, a, [t], ids[0] if ids else "<ID>")
    if not _nur_geldbewegung(lauf, t):
        raise ZuordnungError(
            f"{markt} {a.nummer}: der Bankumsatz {str(t.id)[:8]} ist schon gebucht "
            f"({', '.join(ids)}) — erst korrigieren mit {befehl} (die Auszahlung ist "
            "eine Geldbewegung ohne Umsatzsteuer), dann zuordnen"
        )
    if _vorgebucht(lauf, a, t) is None:
        raise ZuordnungError(
            f"{markt} {a.nummer}: der Bankumsatz {str(t.id)[:8]} ist als Geldbewegung "
            f"auf einem anderen Konto gebucht ({', '.join(ids)}), nicht auf "
            f"{_gegenkonto(lauf.kontext, a)} — erst umbuchen mit {befehl}, dann "
            "zuordnen"
        )


def _loese(
    session: Session,
    kontext: Kontext,
    a: Abrechnung,
    p: Marktplatzposten,
    t: Transaktion,
    person: str,
    datum: date | None,
    kr: Kontenrahmen,
) -> tuple[str, list[str]]:
    """Löst die Zuordnung des Postens zum Umsatz: accountis Buchungen dazu (``_buche``:
    Bank an Gegenkonto mit der Kursdifferenz, bzw. nur die umgebuchte Kursdifferenz)
    werden storniert, ein Vorschlag verworfen; die Befunde dieser Zuordnung sind
    erledigt. Eine Korrektur des Menschen am Umsatz (Geldbewegung auf dem
    Gegenkonto) bleibt — der Umsatz ist dann für eine andere Abrechnung
    ``_vorgebucht``."""
    from accounti.db.repo_bank import loesche_buchung
    from accounti.db.repository import lade_belegbuchungen
    from accounti.pruefung.storno import StornoError, ist_freigegeben, storniere

    markt = ANZEIGE.get(a.marktplatz, a.marktplatz)
    texte = {f"{markt} {art} {a.nummer}"[:60] for art in ("Auszahlung", "Einzahlung")}
    kurs = f"{markt} Kursdifferenz {a.nummer}"[:60]
    eigene = [
        b
        for b in buchungen_zur_transaktion(session, t.id)
        if b.beleg_id == a.beleg_id and b.buchungstext in texte | {kurs}
    ]
    if a.beleg_id is not None:
        eigene += [
            b
            for b in lade_belegbuchungen(session, a.beleg_id)
            if b.buchungstext == kurs and b.datum == t.datum
        ]
    grund = (
        f"{markt} {a.nummer}: Zuordnung zum Bankumsatz vom {t.datum:%d.%m.%Y} von "
        "Hand gelöst"
    )
    warnungen: list[str] = []
    for b in eigene:
        if ist_freigegeben(b):
            try:
                k = storniere(
                    session,
                    str(b.id),
                    grund=grund,
                    von=person,
                    datum=datum,
                    kontenrahmen=kr,
                )
            except StornoError as fehler:
                raise ZuordnungError(
                    f"{markt} {a.nummer}: {fehler} (accounti marktplatz zuordnen … "
                    "--datum JJJJ-MM-TT)"
                ) from fehler
            warnungen.extend(k.warnungen)
        else:
            loesche_buchung(session, b.id)
    setze_bank_transaktion(session, p.id, None)
    p.bank_transaktion_id = None
    erledigt = [
        x
        for x in a.offene_befunde
        if x.posten_nr == p.nr
        and x.code in ABGLEICHSBEFUNDE | {OHNE_NUMMER, VON_HAND, "kursdifferenz"}
    ]
    for x in erledigt:
        x.erledigt = True
    erledige_befunde(session, [x.id for x in erledigt])
    a.status = status_von(a)
    setze_abrechnungsstatus(session, a.id, a.status)
    session.flush()
    return (
        f"{markt} {a.nummer}: Zuordnung zum Bankumsatz vom {t.datum:%d.%m.%Y} über "
        f"{eur_text(t.betrag)} € ({str(t.id)[:8]}) gelöst — "
        f"{len(eigene)} Buchung(en) storniert bzw. verworfen"
    ), warnungen
