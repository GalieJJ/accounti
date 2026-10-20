"""Tagesübersicht über eine Kanal-Registry — gebündelt statt Einzelmeldungen.

Je Empfänger (Benutzer, ``@rolle`` oder ``gemeinsam``) entsteht am Tag höchstens eine
Übersicht: fällige Aufgaben und Erinnerungen, neue Aufgaben, Eskalationen. Wer keine
Adresse unter ``aufgaben.benachrichtigung.empfaenger`` hat, landet in der Übersicht
der gemeinsamen Liste — eine Aufgabe verschwindet nicht, nur weil niemand eine
Adresse eingetragen hat.

Kanäle: ``email`` (SMTP-Zugang und Absender aus dem Abschnitt ``versand``, derselbe
Versandweg wie für Rechnungen) und ``webhook`` (JSON mit ``text`` für Slack,
Mattermost & Co.). Jeder Versuch steht im Protokoll ``aufgaben_benachrichtigungen``
— auch ein unerwarteter Fehler eines Kanals ist nur ein Fehlschlag dieser
Zustellung. Als gemeldet (Stufe, „neu“) gilt eine Aufgabe erst, wenn jeder Kanal sie
heute zugestellt hat, eine Eskalation erst, wenn auch die Kopie an das
Eskalationsziel überall ankam — ein Ausfall holt der nächste Lauf nach.
"""

from __future__ import annotations

import http.client
import json
import re
import urllib.error
import urllib.request
from collections import defaultdict
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import date, datetime
from email.headerregistry import Address
from email.message import EmailMessage
from email.utils import format_datetime, getaddresses, make_msgid, parseaddr
from pathlib import Path
from typing import Any, Literal, Protocol
from urllib.parse import urlsplit

from sqlalchemy.orm import Session

from accounti.anzeige import datum_de
from accounti.aufgaben.anbindung import lade_anbindungen
from accounti.aufgaben.einstellungen import AufgabenEinstellungen
from accounti.aufgaben.erinnerung import Erinnerung, faellige_erinnerungen
from accounti.aufgaben.zustaendigkeit import GEMEINSAM
from accounti.db.repo_aufgaben import (
    AufgabeVeraltetError,
    aktualisiere_aufgabe,
    lade_aufgaben,
    lade_benachrichtigungen,
    speichere_benachrichtigung,
    speichere_kommentar,
)
from accounti.erechnung.versand import SmtpVersand, Versandweg, lade_versand
from accounti.konfiguration import KonfigurationError
from accounti.models.aufgaben import (
    AKTIVE_STATUS,
    Aufgabe,
    Benachrichtigung,
    Kommentar,
    KommentarArt,
    Prioritaet,
)

Abschnitt = Literal["faellig", "neu", "eskaliert"]
_UEBERSCHRIFTEN: dict[str, str] = {
    "faellig": "Fällig und Erinnerungen",
    "neu": "Neu",
    "eskaliert": "Eskaliert",
}


class KanalError(RuntimeError):
    """Ein Kanal konnte die Tagesübersicht nicht zustellen."""


@dataclass
class Eintrag:
    aufgabe: Aufgabe
    abschnitt: Abschnitt
    erinnerung: Erinnerung | None = None
    # Empfänger der Eskalationskopie, wenn es eine eigene Übersicht dafür gibt
    kopie_an: str | None = None


_ERWAEHNUNG = re.compile(r"@(?=\w)")


def fuer_chat(text: str) -> str:
    """Text für Slack, Mattermost & Co. entschärfen — Titel enthalten Fremddaten
    (Kontaktname, Dateiname, Buchungstext). ``&``, ``<``, ``>`` werden maskiert
    (Slack liest sie sonst als Steuerzeichen: ``<!channel>``, ``<URL|Text>``),
    Markdown-Links ``[Text](URL)`` und @-Erwähnungen mit einem unsichtbaren
    Leerzeichen gebrochen."""
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    text = text.replace("](", "]\u200b(")
    return _ERWAEHNUNG.sub("@\u200b", text)


@dataclass
class Tagesuebersicht:
    empfaenger: str  # Benutzer, "@rolle" oder "gemeinsam"
    tag: date
    eintraege: list[Eintrag] = field(default_factory=list)
    offen: int = 0
    ueberfaellig: int = 0

    @property
    def nummern(self) -> list[int]:
        return sorted({e.aufgabe.nr for e in self.eintraege})

    def anzahl(self, abschnitt: Abschnitt) -> int:
        return sum(1 for e in self.eintraege if e.abschnitt == abschnitt)

    def betreff(self) -> str:
        teile = [
            f"{n} {wort}"
            for wort, n in (
                ("fällig", self.anzahl("faellig")),
                ("neu", self.anzahl("neu")),
                ("eskaliert", self.anzahl("eskaliert")),
            )
            if n
        ]
        return f"accounti: {', '.join(teile)} — Aufgaben am {datum_de(self.tag)}"

    def _fuer_wen(self) -> tuple[str, str]:
        if self.empfaenger == GEMEINSAM:
            return "Gemeinsame Liste", "accounti aufgaben liste --unzugewiesen"
        if self.empfaenger.startswith("@"):
            rolle = self.empfaenger[1:]
            return f"Aufgaben der Rolle {rolle}", "accounti aufgaben liste --alle"
        return (
            f"Aufgaben für {self.empfaenger}",
            f"accounti aufgaben liste --zustaendig {self.empfaenger}",
        )

    def text(self) -> str:
        kopf, befehl = self._fuer_wen()
        zeilen = [f"{kopf} — Tagesübersicht vom {datum_de(self.tag)}", ""]
        for abschnitt, ueberschrift in _UEBERSCHRIFTEN.items():
            eintraege = [e for e in self.eintraege if e.abschnitt == abschnitt]
            if not eintraege:
                continue
            zeilen.append(f"{ueberschrift} ({len(eintraege)})")
            for e in sorted(eintraege, key=lambda x: x.aufgabe.nr):
                a = e.aufgabe
                zeilen.append(f"  #{a.nr}  {a.titel}")
                details = [f"fällig {datum_de(a.faellig_am)}"]
                if e.erinnerung is not None:
                    details.append(e.erinnerung.bezeichnung)
                if a.prioritaet is Prioritaet.HOCH:
                    details.append("Priorität hoch")
                if a.zustaendigkeit != self.empfaenger:
                    details.append(f"zuständig: {a.zustaendigkeit}")
                zeilen.append(f"      {' · '.join(details)}")
            zeilen.append("")
        zeilen.append(
            f"Offen insgesamt: {self.offen}, davon überfällig: {self.ueberfaellig}."
        )
        zeilen.append(f"Alle Aufgaben: {befehl}")
        zeilen.append(
            "Einzelne Aufgabe: accounti aufgaben zeige NR · erledigen: "
            "accounti aufgaben erledigen NR"
        )
        return "\n".join(zeilen) + "\n"

    def als_json(self) -> dict[str, Any]:
        return {
            # Slack, Mattermost & Co. zeigen dieses Feld — entschärft; die Felder
            # unten bleiben roh, wer sie anzeigt, maskiert selbst
            "text": fuer_chat(self.text()),
            "empfaenger": self.empfaenger,
            "tag": self.tag.isoformat(),
            "offen": self.offen,
            "ueberfaellig": self.ueberfaellig,
            "aufgaben": [
                {
                    "nr": e.aufgabe.nr,
                    "art": e.aufgabe.art,
                    "titel": e.aufgabe.titel,
                    "objekt": str(e.aufgabe.objekt),
                    "faellig_am": e.aufgabe.faellig_am.isoformat()
                    if e.aufgabe.faellig_am
                    else None,
                    "status": e.aufgabe.status.value,
                    "prioritaet": e.aufgabe.prioritaet.value,
                    "zustaendig": e.aufgabe.zustaendigkeit,
                    "abschnitt": e.abschnitt,
                    "stufe": e.erinnerung.stufe if e.erinnerung else 0,
                }
                for e in sorted(self.eintraege, key=lambda x: x.aufgabe.nr)
            ],
        }


def empfaenger_von(ziel: str, einstellungen: AufgabenEinstellungen) -> str:
    """Benutzer oder ``@rolle`` mit Adresse — sonst die gemeinsame Liste."""
    if ziel in einstellungen.benachrichtigung.empfaenger:
        return ziel
    return GEMEINSAM


def stelle_zusammen(
    session: Session, einstellungen: AufgabenEinstellungen, stichtag: date
) -> list[Tagesuebersicht]:
    """Die Tagesübersichten des Stichtags — ändert nichts (auch für die Vorschau)."""
    aktive = lade_aufgaben(session, status=AKTIVE_STATUS)
    erinnerungen = {
        e.aufgabe.id: e for e in faellige_erinnerungen(aktive, einstellungen, stichtag)
    }
    uebersichten: dict[str, Tagesuebersicht] = {}

    def uebersicht(schluessel: str) -> Tagesuebersicht:
        if schluessel not in uebersichten:
            uebersichten[schluessel] = Tagesuebersicht(schluessel, stichtag)
        return uebersichten[schluessel]

    for a in aktive:
        schluessel = empfaenger_von(a.zustaendigkeit, einstellungen)
        u = uebersicht(schluessel)
        u.offen += 1
        if a.faellig_am is not None and a.faellig_am < stichtag:
            u.ueberfaellig += 1
        erinnerung = erinnerungen.get(a.id)
        if erinnerung is not None:
            eintrag = Eintrag(a, "faellig", erinnerung)
            u.eintraege.append(eintrag)
            if erinnerung.eskaliert_an:
                ziel = empfaenger_von(erinnerung.eskaliert_an, einstellungen)
                if ziel != schluessel:
                    eintrag.kopie_an = ziel
                    uebersicht(ziel).eintraege.append(
                        Eintrag(a, "eskaliert", erinnerung)
                    )
        elif einstellungen.benachrichtigung.neue_melden and a.gemeldet_am is None:
            u.eintraege.append(Eintrag(a, "neu"))
    return [uebersichten[k] for k in sorted(uebersichten) if uebersichten[k].eintraege]


# ---------------------------------------------------------------------------
# Kanäle
# ---------------------------------------------------------------------------


class Kanal(Protocol):
    name: str

    def adresse(self, uebersicht: Tagesuebersicht) -> str | None: ...

    def sende(self, uebersicht: Tagesuebersicht) -> None: ...


class EmailKanal:
    """Eine E-Mail je Tagesübersicht über den SMTP-Zugang aus ``versand``."""

    name = "email"

    def __init__(
        self,
        empfaenger: Mapping[str, str],
        absender: str,
        versandweg: Versandweg,
        jetzt: Callable[[], datetime] = datetime.now,
    ) -> None:
        self.empfaenger = dict(empfaenger)
        self.absender = absender
        self.versandweg = versandweg
        self.jetzt = jetzt

    def adresse(self, uebersicht: Tagesuebersicht) -> str | None:
        return self.empfaenger.get(uebersicht.empfaenger)

    def baue(self, uebersicht: Tagesuebersicht, an: str) -> EmailMessage:
        nachricht = EmailMessage()
        nachricht["From"] = self.absender
        nachricht["To"] = an
        nachricht["Subject"] = uebersicht.betreff()
        nachricht["Date"] = format_datetime(self.jetzt().astimezone())
        domain = Address(addr_spec=parseaddr(self.absender)[1]).domain
        nachricht["Message-ID"] = make_msgid(domain=domain or None)
        # RFC 3834: automatisch erzeugt — Abwesenheitsnotizen antworten nicht darauf
        nachricht["Auto-Submitted"] = "auto-generated"
        nachricht.set_content(uebersicht.text())
        return nachricht

    def sende(self, uebersicht: Tagesuebersicht) -> None:
        an = self.adresse(uebersicht)
        if not an or not any(addr for _, addr in getaddresses([an])):
            msg = (
                f"Keine E-Mail-Adresse für '{uebersicht.empfaenger}' — "
                f"aufgaben.benachrichtigung.empfaenger.{uebersicht.empfaenger} "
                "eintragen"
            )
            raise KanalError(msg)
        self.versandweg.sende(self.baue(uebersicht, an))


class WebhookKanal:
    """Ein ``POST`` mit JSON je Tagesübersicht (Feld ``text`` plus Einzelheiten)."""

    name = "webhook"

    def __init__(self, url: str, timeout: float = 10) -> None:
        self.url = url
        self.timeout = timeout

    def _ziel(self) -> str:
        teile = urlsplit(self.url)  # Pfad und Abfrage tragen oft ein Geheimnis
        if not teile.scheme or not teile.netloc:
            return "(ungültige Adresse)"
        return f"{teile.scheme}://{teile.netloc}/…"

    def adresse(self, uebersicht: Tagesuebersicht) -> str | None:
        return self._ziel()

    def sende(self, uebersicht: Tagesuebersicht) -> None:
        daten = json.dumps(uebersicht.als_json(), ensure_ascii=False).encode("utf-8")
        try:
            anfrage = urllib.request.Request(
                self.url,
                data=daten,
                method="POST",
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(anfrage, timeout=self.timeout) as antwort:
                status = antwort.status
        except urllib.error.HTTPError as fehler:
            status = fehler.code
        except urllib.error.URLError as fehler:
            msg = f"Webhook {self._ziel()} nicht erreichbar: {fehler.reason}"
            raise KanalError(msg) from fehler
        except (OSError, ValueError, http.client.HTTPException) as fehler:
            # ohne den Text des Fehlers: er kann die URL samt Geheimnis enthalten
            msg = f"Webhook {self._ziel()} nicht zustellbar ({type(fehler).__name__})"
            raise KanalError(msg) from fehler
        if not 200 <= status < 300:
            msg = f"Webhook antwortete mit HTTP {status}"
            raise KanalError(msg)


def _email_aus_konfiguration(
    einstellungen: AufgabenEinstellungen, pfad: Path
) -> EmailKanal:
    versand = lade_versand(pfad)
    return EmailKanal(
        einstellungen.benachrichtigung.empfaenger,
        einstellungen.benachrichtigung.absender or versand.absender,
        SmtpVersand(versand),
    )


def _webhook_aus_konfiguration(
    einstellungen: AufgabenEinstellungen, pfad: Path
) -> WebhookKanal:
    webhook = einstellungen.benachrichtigung.webhook
    if webhook is None:
        msg = "aufgaben.benachrichtigung.webhook.url fehlt"
        raise KonfigurationError(msg)
    return WebhookKanal(webhook.url, webhook.timeout_sekunden)


KANAELE: dict[str, Callable[[AufgabenEinstellungen, Path], Kanal]] = {
    "email": _email_aus_konfiguration,
    "webhook": _webhook_aus_konfiguration,
}


def baue_kanaele(
    einstellungen: AufgabenEinstellungen, pfad: str | Path
) -> tuple[dict[str, Kanal], dict[str, str]]:
    """Richtet die konfigurierten Kanäle ein: (Kanäle, Fehler je Kanal)."""
    lade_anbindungen()  # Kanäle anderer Bausteine
    kanaele: dict[str, Kanal] = {}
    fehler: dict[str, str] = {}
    for name in einstellungen.benachrichtigung.kanaele:
        fabrik = KANAELE.get(name)
        if fabrik is None:
            fehler[name] = (
                f"unbekannter Kanal {name} (vorhanden: {', '.join(sorted(KANAELE))})"
            )
            continue
        try:
            kanaele[name] = fabrik(einstellungen, Path(pfad))
        except KonfigurationError as problem:
            fehler[name] = str(problem)
    return kanaele, fehler


# ---------------------------------------------------------------------------
# Versenden
# ---------------------------------------------------------------------------


@dataclass
class Zustellung:
    empfaenger: str
    kanal: str
    nummern: list[int]
    erfolgreich: bool
    adresse: str | None = None
    fehler: str | None = None
    uebersprungen: bool = False  # heute schon zugestellt


@dataclass
class Erinnerungslauf:
    uebersichten: list[Tagesuebersicht] = field(default_factory=list)
    zustellungen: list[Zustellung] = field(default_factory=list)
    gemeldet: list[Aufgabe] = field(default_factory=list)


def versende_tagesuebersichten(
    session: Session,
    einstellungen: AufgabenEinstellungen,
    kanaele: Mapping[str, Kanal],
    *,
    stichtag: date | None = None,
    jetzt: datetime | None = None,
    kanalfehler: Mapping[str, str] | None = None,
    sichern: Callable[[], None] | None = None,
) -> Erinnerungslauf:
    """Stellt die Tagesübersichten zu — je Empfänger und Kanal einmal am Tag.

    ``sichern`` wird nach jeder protokollierten Zustellung aufgerufen (die CLI
    übergibt ``session.commit``): Bricht der Lauf danach ab, steht das Gesendete
    trotzdem im Protokoll, und der nächste Lauf verschickt es nicht noch einmal.
    """
    jetzt = jetzt or datetime.now()
    stichtag = stichtag or jetzt.date()
    kanalfehler = kanalfehler or {}
    namen = list(einstellungen.benachrichtigung.kanaele)
    lauf = Erinnerungslauf(stelle_zusammen(session, einstellungen, stichtag))

    zugestellt: dict[tuple[str, str], set[int]] = defaultdict(set)
    for b in lade_benachrichtigungen(session, tag=stichtag):
        if b.erfolgreich:
            zugestellt[(b.empfaenger, b.kanal)].update(b.aufgaben)
    schon_heute = set(zugestellt)

    for u in lauf.uebersichten:
        for name in namen:
            kanal = kanaele.get(name)
            if (u.empfaenger, name) in schon_heute:
                lauf.zustellungen.append(
                    Zustellung(u.empfaenger, name, u.nummern, True, uebersprungen=True)
                )
                continue
            adresse = kanal.adresse(u) if kanal is not None else None
            fehler: str | None = None
            if kanal is None:
                fehler = kanalfehler.get(name, f"Kanal {name} ist nicht eingerichtet")
            else:
                try:
                    kanal.sende(u)
                except Exception as problem:  # jeder Fehler: nur diese Zustellung
                    fehler = f"{type(problem).__name__}: {problem}"
            speichere_benachrichtigung(
                session,
                Benachrichtigung(
                    tag=stichtag,
                    empfaenger=u.empfaenger,
                    kanal=name,
                    adresse=adresse,
                    aufgaben=u.nummern,
                    erfolgreich=fehler is None,
                    fehler=fehler,
                    zeitpunkt=jetzt,
                ),
            )
            if sichern is not None:
                sichern()
            if fehler is None:
                zugestellt[(u.empfaenger, name)].update(u.nummern)
            lauf.zustellungen.append(
                Zustellung(
                    u.empfaenger, name, u.nummern, fehler is None, adresse, fehler
                )
            )

    def ueberall(nr: int, empfaenger: str) -> bool:
        return all(nr in zugestellt[(empfaenger, n)] for n in namen)

    for u in lauf.uebersichten:
        for e in u.eintraege:
            if e.abschnitt == "eskaliert":
                continue  # Kopie; vermerkt wird am Eintrag des Zuständigen
            if not ueberall(e.aufgabe.nr, u.empfaenger):
                continue
            kopie_da = e.kopie_an is None or ueberall(e.aufgabe.nr, e.kopie_an)
            try:
                lauf.gemeldet.append(_vermerke(session, e, stichtag, jetzt, kopie_da))
            except AufgabeVeraltetError:
                continue  # inzwischen geändert — der nächste Lauf vermerkt
    return lauf


def _vermerke(
    session: Session,
    eintrag: Eintrag,
    stichtag: date,
    jetzt: datetime,
    kopie_da: bool = True,
) -> Aufgabe:
    """Gemeldete Stufe speichern; bei Eskalation Priorität hoch und Verlauf.

    Kam die Kopie an das Eskalationsziel nicht (überall) an, gilt nur die Stufe
    davor als gemeldet — der nächste Lauf eskaliert erneut."""
    a = eintrag.aufgabe
    aenderung: dict[str, object] = {"gemeldet_am": a.gemeldet_am or stichtag}
    er = eintrag.erinnerung
    eskaliert = er is not None and bool(er.eskaliert_an) and kopie_da
    if er is not None:
        stufe = er.stufe if eskaliert or not er.eskaliert_an else er.stufe - 1
        aenderung["erinnerungsstufe"] = max(a.erinnerungsstufe, stufe)
        if eskaliert:
            aenderung["prioritaet"] = Prioritaet.HOCH
    neu = aktualisiere_aufgabe(session, a.model_copy(update=aenderung))
    if er is not None and eskaliert:
        speichere_kommentar(
            session,
            Kommentar(
                aufgabe_id=a.id,
                objekt_typ=a.objekt_typ,
                objekt_id=a.objekt_id,
                art=KommentarArt.EREIGNIS,
                autor="system",
                text=(
                    f"eskaliert an {er.eskaliert_an} "
                    f"({er.ueberfaellig_tage} Tage überfällig, Stufe {er.stufe})"
                ),
                erstellt_am=jetzt,
            ),
        )
    return neu
