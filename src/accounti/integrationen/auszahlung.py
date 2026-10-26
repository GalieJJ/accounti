"""Auszahlung ↔ Bankumsatz: der einzige Abgleichspunkt einer Abrechnung.

Die Regel, welcher Bankumsatz zu welcher Auszahlung gehört, in einem Stück
(``_umsaetze``, ``_kandidaten``, ``_befund``, ``_zweifel``; Nachprüfungen 1–4 E):

1. In Frage kommen Bankumsätze im Zeitfenster um das Auszahlungsdatum mit derselben
   Richtung, die weder früher noch in diesem Lauf einem Marktplatzposten zugeordnet
   sind — nie PayPal-Umsätze oder Umsätze auf einem Verrechnungskonto.
2. Nummer vor Betrag: Nennt ein Umsatz die Nummer einer anderen bekannten Abrechnung
   desselben Marktplatzes (gespeichert oder aus demselben Bericht; als eigenes Wort,
   mindestens 6 Zeichen) und nicht die eigene, gehört er zu ihr — hier weder Treffer
   noch Befund.
3. Nennt ein Umsatz im Fenster die eigene Nummer, zählen nur die eigenen, ob offen,
   als Erlös gebucht oder umgebucht: Kein anderer wird Treffer, auch nicht mit
   exaktem Betrag oder in der Toleranz, und keiner der anderen steht im Befund. Ein
   Umsatz ohne die eigene Nummer kann nur Treffer werden, wenn keiner sie nennt.
4. Nennt ein offener Umsatz statt der eigenen eine andere Nummer derselben Form (nur
   Ziffern, gleiche Länge), die noch keine Abrechnung trägt, ist er wohl die
   Auszahlung einer noch nicht importierten: weder Treffer noch Abweichung. Bleibt
   sonst nichts, ist das die Warnung ``auszahlung_andere_nummer``; mit dem Import
   jener Abrechnung gilt Regel 2, die Warnung erledigt sich. Ist er schon gebucht,
   sagt der Befund „schon gebucht“ dazu, dass er wohl zu einer anderen gehört; hat
   der Mensch ihn danach selbst aufs Gegenkonto gebucht, gilt das (Regel 5) — so
   bleibt ein Ausweg, wenn die Zahl nur eine Referenz der Bank war.
5. Treffer ist ein offener Umsatz — oder einer, der als Geldbewegung schon auf dem
   Gegenkonto steht (die Korrektur nach „schon gebucht“, ``_vorgebucht``) — mit exakt
   dem erwarteten Betrag, in Fremdwährung ohne solchen einer mit Stichwort oder
   Nummer in der Toleranz. Mehrere grenzen Stichwort und eigene Nummer ein; bleiben
   mehrere, ist das ``auszahlung_mehrdeutig`` — es wird nicht geraten.
6. Ohne Treffer gilt der erste dieser Befunde: ein offener Umsatz mit Stichwort oder
   Nummer in anderer Höhe (``auszahlung_abweichung``); ein als Erlös gebuchter mit
   passendem Betrag (``auszahlung_anderweitig_gebucht``, Fehler — die Voranmeldung
   des Bankmonats warnt, ``bankdaten``; mehrere grenzen eigene Nummer, keine andere
   Nummer und exakter Betrag ein, sonst nennt der Befund alle); eine Geldbewegung auf
   einem anderen Konto (``auszahlung_umgebucht``); Regel 4. Sonst ist die Auszahlung
   noch nicht auf der Bank, ohne Befund.
7. Befunde über einen Umsatz (``_UMSATZBEFUNDE``) gelten, solange ein Lauf sie so
   wiederfindet — nennt ein späterer einen anderen oder keinen Umsatz mehr (etwa weil
   die fremde Nummer inzwischen bekannt ist), ist der alte erledigt. Ein Treffer
   erledigt alle Abgleichsbefunde des Postens.
8. Kommt der Umsatz mit der eigenen Nummer erst, nachdem die Auszahlung einem ohne
   sie zugeordnet wurde (als noch keiner sie nannte), und ist er als Erlös gebucht,
   ist das ``auszahlung_anderweitig_gebucht`` an dieser Abrechnung — die
   Voranmeldung seines Monats warnt. Die Zuordnung bleibt.

Grenzen: Ohne Nummer im Verwendungszweck entscheiden Stichwort und Betrag. In
Fremdwährung ist dann geraten, welcher von zwei Umsätzen in der Toleranz zu welcher
Auszahlung gehört (die Kursdifferenzen sind vertauscht, ihre Summe stimmt), und ein
Umsatz ohne Nummer kann Treffer werden, bevor der mit der eigenen Nummer auf der Bank
steht. Einen doppelten Erlös meldet dann ein Befund (Regel 6 oder 8), die
Zuordnung selbst bleibt falsch.

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
from uuid import UUID

from sqlalchemy.orm import Session

from accounti.db.repo_integrationen import (
    abrechnungsnummern,
    ergaenze_befunde,
    erledige_befunde,
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

VORLAUF = timedelta(days=2)  # Bank bucht selten vor dem gemeldeten Auszahlungsdatum


@dataclass
class Abgleich:
    abrechnung: Abrechnung
    posten: Marktplatzposten
    transaktion: Transaktion | None = None
    befund: Befund | None = None


ABGLEICHSBEFUNDE = {
    "auszahlung_abweichung",
    "auszahlung_mehrdeutig",
    "auszahlung_anderweitig_gebucht",
    "auszahlung_umgebucht",
    "auszahlung_andere_nummer",
}
# Befunde über einen bestimmten Umsatz: überholt, sobald ein Lauf ihn nicht mehr so
# findet (``gleiche_auszahlungen_ab``, Regel 7)
_UMSATZBEFUNDE = {
    "auszahlung_anderweitig_gebucht",
    "auszahlung_umgebucht",
    "auszahlung_andere_nummer",
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

    Ergebnis: je offenem Posten ein ``Abgleich``, dazu einer (ohne ``transaktion``)
    für jede frühere Zuordnung, die Regel 8 jetzt bezweifelt.
    """
    e = kontext.einstellungen
    if abrechnungen is None:
        abrechnungen = lade_abrechnungen(session)
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
    offene: list[tuple[Abrechnung, Marktplatzposten, Decimal]] = []
    for a in abrechnungen:
        for p in a.posten:
            if (
                p.art not in (Postenart.AUSZAHLUNG, Postenart.EINZAHLUNG)
                or p.bank_transaktion_id is not None
            ):
                continue
            if a.waehrung != "EUR" and p.betrag_eur is None:
                continue  # ohne Kurs nicht gebucht, also auch nicht abzugleichen
            erwartet = -(p.betrag_eur if p.betrag_eur is not None else p.betrag)
            if erwartet:
                offene.append((a, p, erwartet))

    ergebnisse: dict[UUID, Abgleich] = {}
    weiter = True
    while weiter:
        weiter = False
        for a, p, erwartet in offene:
            if p.id in ergebnisse:
                continue
            kandidaten = _kandidaten(lauf, a, p, erwartet)
            if len(kandidaten) == 1:
                ergebnisse[p.id] = _zuordnen(lauf, a, p, kandidaten[0], erwartet)
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
            # „schon gebucht“ gilt, solange der Lauf denselben Umsatz findet: nennt er
            # einen anderen oder keinen mehr, ist der alte Befund überholt (etwa weil
            # der Umsatz die Nummer einer inzwischen bekannten Abrechnung trägt). Nach
            # „mehrdeutig“/„abweichung“ nicht — dort wird nach gebuchten nicht gesucht
            if neu is None or neu.code in _UMSATZBEFUNDE:
                ueberholt.extend(
                    b
                    for b in a.offene_befunde
                    if b.code in _UMSATZBEFUNDE
                    and b.posten_nr == p.nr
                    and (neu is None or (b.code, b.text) != (neu.code, neu.text))
                )
    # Regel 8: Zuordnungen früherer Läufe ohne die eigene Nummer gegen Umsätze, die
    # sie nennen und inzwischen als Erlös gebucht sind
    zweifel: list[Abgleich] = []
    for a in abrechnungen:
        for p in a.posten:
            if (
                p.art not in (Postenart.AUSZAHLUNG, Postenart.EINZAHLUNG)
                or p.bank_transaktion_id is None
                or p.id in ergebnisse
            ):
                continue
            neu = _zweifel(lauf, a, p)
            if neu is not None:
                neue_befunde.setdefault(a.id, []).append(neu)
                zweifel.append(Abgleich(a, p, befund=neu))
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
    return [ergebnisse[p.id] for _a, p, _e in offene] + zweifel


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
    Ziffern, gleiche Länge, mindestens ``_MINDESTLAENGE``), wenn der Umsatz die eigene
    nicht nennt — die Auszahlungsnummer einer Abrechnung, die accounti noch nicht
    kennt. Leer bei Nummern anderer Form (PayPal-Zeitraum, Shopify ohne ID)."""
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
        and (z.start() == 0 or not text[z.start() - 1].isalnum())
        and (z.end() == len(text) or not text[z.end()].isalnum())
    ]


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
) -> Abgleich:
    """Eindeutiger Treffer: Befunde zu diesem Posten aus früheren Läufen erledigen
    sich; eine Kursdifferenz (Fremdwährung) steht als Hinweis an der Abrechnung.
    Steht der Umsatz schon auf dem Gegenkonto (``_vorgebucht``), wird nur noch die
    Kursdifferenz gebucht, nicht die Bank ein zweites Mal."""
    vorgebucht = _vorgebucht(lauf, a, t)
    erledigt = [
        b
        for b in a.offene_befunde
        if b.code in ABGLEICHSBEFUNDE and b.posten_nr == p.nr
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
    return Abgleich(a, p, t, befund)


def _befund(
    lauf: _Lauf, a: Abrechnung, p: Marktplatzposten, erwartet: Decimal
) -> Abgleich:
    """Regel 6: kein eindeutiger Treffer — mehrdeutig, abweichend, anderweitig
    gebucht, umgebucht, eine andere Nummer — oder einfach noch nicht auf der Bank."""
    markt = ANZEIGE.get(a.marktplatz, a.marktplatz)
    kandidaten = _kandidaten(lauf, a, p, erwartet)
    if kandidaten:
        return Abgleich(
            a,
            p,
            befund=Befund(
                code="auszahlung_mehrdeutig",
                schweregrad=Schweregrad.WARNUNG,
                text=(
                    f"{markt} {a.nummer}: {len(kandidaten)} Bankumsätze über "
                    f"{eur_text(erwartet)} € passen — bitte zuordnen, es wird nicht "
                    "geraten"
                ),
                posten_nr=p.nr,
            ),
        )
    # nur eigene, sonst keine fremden (Regeln 2, 3)
    umsaetze = [t for t in _umsaetze(lauf, a, p, erwartet) if _erkennbar(lauf, a, t)]
    anders = [
        t
        for t in umsaetze
        if t.id in lauf.offen_ids and t.betrag != erwartet and not _andere_nummern(a, t)
    ]
    if anders:
        (t, *_) = _eingrenzen(anders, lambda t: _eigene_nummer(a, t))
        return Abgleich(
            a,
            p,
            befund=Befund(
                code="auszahlung_abweichung",
                schweregrad=Schweregrad.FEHLER,
                text=(
                    f"{markt} {a.nummer}: Bankumsatz vom {t.datum:%d.%m.%Y} über "
                    f"{eur_text(t.betrag)} € ≠ Auszahlung laut Abrechnung "
                    f"{eur_text(erwartet)} € — nicht gebucht, Differenz klären"
                ),
                posten_nr=p.nr,
            ),
        )

    # Fremdwährung: dieselbe Toleranz wie beim Treffer — die Bank rechnet mit ihrem
    # eigenen Kurs, exakt gleich ist der gebuchte Umsatz fast nie (sonst stünde der
    # Erlös still doppelt in der Voranmeldung). Ein zugeordneter oder fremder Umsatz
    # (``_umsaetze``) und eine Geldbewegung sind nicht „schon gebucht“ — sonst träfe
    # die Toleranz den Umsatz der vorigen Auszahlung (Nachprüfung 2 E, M1; 3 E, M2);
    # nennt einer die eigene Nummer, nur er (4 E, M3)
    gebucht = [
        t for t in umsaetze if t.id in lauf.gebucht and _passt(lauf, a, t, erwartet)
    ]
    # mehrere: die eigene Nummer, keine andere, dann der exakte Betrag (in
    # Fremdwährung Zufall, die Nummer nicht; in Euro sind ohnehin alle exakt) —
    # sonst alle nennen
    merkmale: tuple[Callable[[Transaktion], bool], ...] = (
        lambda t: _eigene_nummer(a, t),
        lambda t: not _andere_nummern(a, t),
        lambda t: t.betrag == erwartet,
    )
    schon = _eingrenzen(
        [t for t in gebucht if not _nur_geldbewegung(lauf, t)], *merkmale
    )
    if schon:
        return Abgleich(a, p, befund=_schon_gebucht(lauf, a, p, schon))
    # eine Geldbewegung, aber auf einem anderen Konto (z. B. Geldtransit statt
    # Verrechnungskonto): kein doppelter Erlös, doch die Auszahlung bliebe still
    # offen und das Verrechnungskonto mit Saldo (Nachprüfung 3 E, L-b)
    umgebucht = _eingrenzen(
        [
            t
            for t in gebucht
            if _nur_geldbewegung(lauf, t) and _vorgebucht(lauf, a, t) is None
        ],
        *merkmale,
    )
    if umgebucht:
        return Abgleich(a, p, befund=_umgebucht(lauf, a, p, umgebucht))
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
        return Abgleich(a, p, befund=_andere_nummer(a, p, andere))
    return Abgleich(a, p)


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


def _zweifel(lauf: _Lauf, a: Abrechnung, p: Marktplatzposten) -> Befund | None:
    """Regel 8: Die Auszahlung ist einem Umsatz zugeordnet, der ihre Nummer nicht
    nennt (Stichwort und Betrag — damals nannte sie keiner). Steht jetzt im Fenster
    einer mit der Nummer, als Erlös gebucht, sind die Erlöse doppelt: Fehler „schon
    gebucht“, die Voranmeldung seines Monats warnt. Die Zuordnung bleibt — sie
    zurückzunehmen hieße, accountis Buchung am anderen Umsatz zu stornieren."""
    if a.waehrung != "EUR" and p.betrag_eur is None:
        return None
    erwartet = -(p.betrag_eur if p.betrag_eur is not None else p.betrag)
    if not erwartet or len(a.nummer) < _MINDESTLAENGE:
        return None
    von, bis = _fenster(lauf, p)
    eigene = [
        t
        for t in _nennende(lauf, a)
        if von <= t.datum <= bis
        and t.id not in lauf.zugeordnet
        and t.id not in lauf.benutzt
        and t.id in lauf.gebucht
        and _passt(lauf, a, t, erwartet)
        and not _nur_geldbewegung(lauf, t)
    ]
    if not eigene:
        return None
    zugeordnet = next(
        (t for t in lauf.bankumsaetze if t.id == p.bank_transaktion_id), None
    )
    if zugeordnet is None or _eigene_nummer(a, zugeordnet):
        return None
    befund = _schon_gebucht(lauf, a, p, eigene)
    return befund.model_copy(
        update={
            "text": (
                f"{befund.text}. Zugeordnet ist aber der Bankumsatz vom "
                f"{zugeordnet.datum:%d.%m.%Y}, der {a.nummer} nicht nennt — einer "
                "von beiden gehört nicht zu dieser Auszahlung; die Zuordnung bleibt, "
                "gehört er zu einer anderen Abrechnung, bleibt deren Auszahlung offen"
            )
        }
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
    lauf: _Lauf, a: Abrechnung, p: Marktplatzposten, schon: list[Transaktion]
) -> Befund:
    """FEHLER ``auszahlung_anderweitig_gebucht``: ein Umsatz — oder, nicht
    entscheidbar, mehrere — schon als Erlös gebucht; ``bankdaten`` liest die Tage."""
    markt = ANZEIGE.get(a.marktplatz, a.marktplatz)
    if len(schon) == 1:
        (t,) = schon
        ids = [str(b.id)[:8] for b in _buchungen(lauf, t)]
        befehl = _umbuchung(lauf, a, schon, ids[0] if ids else "<ID>")
        # Regel 4: nennt er eine andere Nummer, gehört er wohl zu einer noch nicht
        # importierten Abrechnung — dann erledigt deren Import den Befund
        andere = _andere_nummern(a, t)
        vorbehalt = (
            f" Er nennt {', '.join(andere)}, nicht {a.nummer} — gehört er zu einer "
            "noch nicht importierten Abrechnung, erst diese importieren, dann "
            "erledigt sich der Befund. Sonst korrigieren"
            if andere
            else " Korrigieren"
        )
        text = (
            f"{markt} {a.nummer}: {_SCHON_GEBUCHT.format(tag=t.datum)} "
            f"({', '.join(ids)}) — Erlöse wären doppelt.{vorbehalt} mit {befehl} "
            "(die Auszahlung ist eine Geldbewegung ohne Umsatzsteuer)"
        )
    else:
        liste, ident = _liste(lauf, schon)
        text = (
            f"{markt} {a.nummer}: {len(schon)} {_SCHON_GEBUCHT_MEHRERE} ({liste}) — "
            "einer davon ist die Auszahlung, ihre Erlöse wären doppelt; welcher, "
            "nennt kein Verwendungszweck, es wird nicht geraten. Den richtigen "
            f"korrigieren mit {_umbuchung(lauf, a, schon, ident)} (die Auszahlung "
            "ist eine Geldbewegung ohne Umsatzsteuer)"
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
    noch nicht importiert ist."""
    markt = ANZEIGE.get(a.marktplatz, a.marktplatz)
    teile = "; ".join(
        f"vom {t.datum:%d.%m.%Y} über {eur_text(t.betrag)} € "
        f"(„{', '.join(_andere_nummern(a, t))}“)"
        for t in umsaetze
    )
    wer = "Der Bankumsatz" if len(umsaetze) == 1 else f"{len(umsaetze)} Bankumsätze"
    return Befund(
        code="auszahlung_andere_nummer",
        schweregrad=Schweregrad.WARNUNG,
        text=(
            f"{markt} {a.nummer}: {wer} {teile} passt im Betrag, nennt aber eine "
            f"andere Nummer statt {a.nummer} — wohl die Auszahlung einer noch nicht "
            "importierten Abrechnung, nicht zugeordnet. Mit deren Import erledigt "
            "sich das; ist er doch diese Auszahlung, den Verwendungszweck prüfen"
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
