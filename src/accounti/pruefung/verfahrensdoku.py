"""Verfahrensdokumentation (Spec 4.6) — aus dem tatsächlichen Systemzustand erzeugt.

Gegliedert wie GoBD Rz. 151 ff.: allgemeine Beschreibung, Anwenderdokumentation,
technische Systemdokumentation, Betriebsdokumentation. Jeder Abschnitt liest, was
eingerichtet ist — Konfiguration (Belegkanäle, Bank, Prüfregeln, Aufgaben,
Zahlungsverkehr, ELSTER), Datenbank (Bankkonten, festgeschriebene Zeiträume, Bestand,
Journal) und die Standardwerte im Code (Auto-Buchen-Schwelle, LLM-Modelle) —, nie
einen Textbaustein. Geheimnisse (Passwörter, Tokens, Produkt-ID) erscheinen nur als
„eingerichtet“.

Jede erzeugte Fassung steht mit ihrem SHA-256 im Journal (``verfahrensdoku_erstellt``)
— so ist die Änderungshistorie nachvollziehbar (Rz. 154), und die nächste Fassung
listet ihre Vorgänger.
"""

from __future__ import annotations

import hashlib
import inspect
import os
import shutil
from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import yaml
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from accounti import __version__
from accounti.anzeige import datum_de
from accounti.konfiguration import STANDARD_PFAD, KonfigurationError
from accounti.models.pruefung import Journaleintrag

VORGANG = "verfahrensdoku_erstellt"


def _zelle(wert: object) -> str:
    return str(wert).replace("|", "/").replace("\n", " ") if wert is not None else "—"


def _tabelle(kopf: list[str], zeilen: list[list[object]]) -> list[str]:
    if not zeilen:
        return ["_(keine)_", ""]
    return [
        "| " + " | ".join(kopf) + " |",
        "|" + "|".join("---" for _ in kopf) + "|",
        *("| " + " | ".join(_zelle(z) for z in zeile) + " |" for zeile in zeilen),
        "",
    ]


def _ja(wert: object) -> str:
    return "ja" if wert else "nein"


_ZEITRAUM = {"monat": "monatlich", "quartal": "vierteljährlich"}


def schwellen_text(werte: dict[str, Any]) -> str:
    """Schwellen einer Regel lesbar: ``ab_betrag=5, belegarten=eingangsrechnung``."""
    teile = []
    for k, v in werte.items():
        if isinstance(v, list):
            v = "/".join(str(x) for x in v)
        teile.append(f"{k}={v}")
    return ", ".join(teile)


class _Doku:
    def __init__(self, session: Session, config: Path, db_url: str | None) -> None:
        self.s = session
        self.config = config
        self.db_url = db_url
        self.zeilen: list[str] = []

    def __call__(self, *zeilen: str) -> None:
        self.zeilen.extend(zeilen)

    def lade(self, lader: Callable[[Path], Any], name: str) -> Any:
        """Abschnitt laden; ein Fehler steht im Dokument, statt es abzubrechen."""
        try:
            return lader(self.config)
        except (KonfigurationError, ValueError) as fehler:
            self(f"> **Konfiguration {name} fehlerhaft:** {_zelle(fehler)}", "")
            return None

    def roh(self) -> dict[str, Any]:
        if not self.config.is_file():
            return {}
        daten: Any = yaml.safe_load(self.config.read_text(encoding="utf-8")) or {}
        return daten if isinstance(daten, dict) else {}

    def anzahl(self, tabelle: Any) -> int:
        return int(
            self.s.execute(select(func.count()).select_from(tabelle)).scalar() or 0
        )


# --- 1 Allgemeine Beschreibung -----------------------------------------------------


def _allgemein(d: _Doku) -> None:
    from accounti.abschluss.konfiguration import lade_abschluss
    from accounti.db.tabellen import (
        BelegRow,
        BuchungssatzRow,
        KontaktRow,
        TransaktionRow,
    )
    from accounti.elster.konfiguration import lade_elster
    from accounti.konfiguration import lade_buchhaltung

    mandant = d.roh().get("mandant") or {}
    anschrift = mandant.get("anschrift") or {}
    d("## 1 Allgemeine Beschreibung", "")
    d(
        f"- **Unternehmen:** {_zelle(mandant.get('name') or 'nicht eingerichtet')}",
        f"- **Anschrift:** {_zelle(anschrift.get('strasse'))}, "
        f"{_zelle(anschrift.get('plz'))} {_zelle(anschrift.get('ort'))}",
        f"- **USt-IdNr.:** {_zelle(mandant.get('ust_id'))} · **Steuernummer:** "
        f"{_zelle(mandant.get('steuernummer'))}",
    )
    buchhaltung = d.lade(lade_buchhaltung, "buchhaltung")
    if buchhaltung is not None:
        d(
            f"- **Kontenrahmen:** {buchhaltung.kontenrahmen}; Debitoren "
            f"{buchhaltung.debitoren_von}–{buchhaltung.debitoren_bis}, Kreditoren "
            f"{buchhaltung.kreditoren_von}–{buchhaltung.kreditoren_bis}; Bank "
            f"{buchhaltung.bank_konto}, Standardaufwand {buchhaltung.standard_aufwand}",
        )
    abschluss = d.lade(lade_abschluss, "abschluss")
    if abschluss is not None:
        art = (
            "Einnahmenüberschussrechnung"
            if abschluss.gewinnermittlung == "euer"
            else "Bilanz"
        )
        d(f"- **Gewinnermittlung:** {art}")
    elster = d.lade(lade_elster, "elster")
    if elster is not None:
        d(
            "- **Umsatzsteuer-Voranmeldung:** "
            f"{_ZEITRAUM[elster.voranmeldungszeitraum]}, "
            f"Dauerfristverlängerung {_ja(elster.dauerfristverlaengerung)}",
        )
    dialekt = urlsplit(d.db_url).scheme.split("+")[0] if d.db_url else "unbekannt"
    zeitraum = d.s.execute(
        select(func.min(BuchungssatzRow.datum), func.max(BuchungssatzRow.datum))
    ).one()
    d(
        f"- **Software:** accounti {__version__} (Open Source, MIT), Datenbank "
        f"{dialekt}",
        f"- **Bestand:** {d.anzahl(BuchungssatzRow)} Buchungen "
        f"({datum_de(zeitraum[0])} bis {datum_de(zeitraum[1])}), "
        f"{d.anzahl(BelegRow)} Belege, {d.anzahl(TransaktionRow)} Bankumsätze, "
        f"{d.anzahl(KontaktRow)} Kontakte",
        "",
    )


# --- 2 Anwenderdokumentation ------------------------------------------------------


def _belegeingang(d: _Doku) -> None:
    from accounti.belege.archiv import AUFBEWAHRUNG_JAHRE
    from accounti.belege.kanaele.einstellungen import lade_belegkanaele
    from accounti.belege.llm import LLMBelegEngine

    d("### 2.1 Belegeingang und Erkennung", "")
    kanaele = d.lade(lade_belegkanaele, "belegkanaele")
    d("Eingerichtete Kanäle (Ordner und Upload stehen immer zur Verfügung):", "")
    if kanaele is not None:
        zeilen: list[list[object]] = [["ordner", "—", "accounti belege import"]]
        zeilen.append(["upload", "—", "Webhook/Upload"])
        for p in kanaele.email:
            zeilen.append(
                [
                    "email",
                    p.name,
                    f"IMAP {p.host}:{p.port_oder_standard} ({p.verschluesselung}), "
                    f"Benutzer {p.benutzer}, Ordner {p.ordner}, danach "
                    f"{p.nach_abholen}",
                ]
            )
        if "webhook" in (d.roh().get("belegkanaele") or {}):
            w = kanaele.webhook
            zeilen.append(["webhook", "—", f"{w.host}:{w.port}, Bearer-Token"])
        for c in kanaele.connectoren:
            basis = str(c.einstellungen().get("basis_url") or "")
            zeilen.append(["connector", c.name, f"{c.typ}: {urlsplit(basis).netloc}"])
        d(*_tabelle(["Kanal", "Name", "Einstellung"], zeilen))
        d(
            f"Dateiprüfung je Kanal: höchstens {kanaele.max_groesse_mb} MB, Typen "
            f"{', '.join(kanaele.dateitypen)} (Typ am Inhalt geprüft).",
            "",
        )
    llm = inspect.signature(LLMBelegEngine).parameters["model"].default
    d(
        "Erkennung: strukturierte E-Rechnung (XRechnung, ZUGFeRD) vor Textebene, "
        "Textebene vor OCR. OCR lokal mit Tesseract "
        f"({'installiert' if shutil.which('tesseract') else 'nicht installiert'}). "
        f"Eine LLM-Stufe ({llm}) läuft nur auf ausdrücklichen Wunsch (--llm) und "
        "erhält den Belegtext maskiert (IBAN, USt-IdNr., Namen, Nummern).",
        "",
        f"Archiv: Originaldateien unverändert, unter ihrem SHA-256 abgelegt, "
        f"schreibgeschützt, ohne Löschpfad; Aufbewahrung {AUFBEWAHRUNG_JAHRE} Jahre "
        "ab Ende des Eingangsjahres (§ 147 Abs. 3, 4 AO). Dubletten werden über "
        "Datei-Hash, Lieferant und Nummer, Betrag und Datum erkannt und verworfen "
        "bzw. zur Prüfung vorgelegt.",
        "",
    )


def _bank(d: _Doku) -> None:
    from accounti.bank.einstellungen import lade_bank_einstellungen
    from accounti.db.repository import lade_bankkonten

    d("### 2.2 Bankumsätze", "")
    konten = lade_bankkonten(d.s)
    d(
        *_tabelle(
            ["Bezeichnung", "IBAN", "Sachkonto", "Provider", "Abrufstand", "Zustand"],
            [
                [
                    k.bezeichnung,
                    k.iban,
                    k.sachkonto,
                    k.provider,
                    datum_de(k.abrufstand),
                    k.zustand.value,
                ]
                for k in konten
            ],
        )
    )
    bank = d.lade(lade_bank_einstellungen, "bank")
    if bank is not None:
        d(
            f"FinTS-Produktregistrierung eingerichtet: {_ja(bank.fints.produkt_id)}. "
            "Zugangsdaten liegen AES-GCM-verschlüsselt am Konto (Schlüssel aus "
            "ACCOUNTI_SCHLUESSEL). Ohne Live-Anbindung werden Kontoauszüge als Datei "
            "(CSV-Profile, MT940, CAMT) importiert; doppelte Umsätze verhindert ein "
            "Dublettenschlüssel.",
            "",
        )


def _kontierung(d: _Doku) -> None:
    from accounti.buchung.mapper import zu_buchungssatz
    from accounti.klassifikation.engine import STANDARD_REGELN
    from accounti.klassifikation.llm import LLMEngine
    from accounti.klassifikation.regeln_loader import lade_regeln

    d("### 2.3 Kontierung", "")
    regeln_datei = Path("config/regeln.yaml")  # wie classify: im Arbeitsverzeichnis
    eigene = lade_regeln(regeln_datei) if regeln_datei.is_file() else []
    schwelle = inspect.signature(zu_buchungssatz).parameters["auto_schwelle"].default
    llm = inspect.signature(LLMEngine).parameters
    d(
        f"Reihenfolge: Beleg (Belegabgleich, offene Posten) → Regelwerk → LLM. "
        f"Regelwerk: {len(eigene)} eigene Regeln ({_zelle(regeln_datei)}) vor "
        f"{len(STANDARD_REGELN)} Standardregeln.",
        "",
    )
    if eigene:
        d(
            *_tabelle(
                ["Regel", "Muster", "Soll", "Haben", "Schlüssel"],
                [
                    [r.name, r.muster, r.soll_konto, r.haben_konto, r.steuer_schluessel]
                    for r in eigene[:40]
                ],
            )
        )
    d(
        f"LLM-Stufe: Modell {llm['model'].default}, Ergebnis nur ab Confidence "
        f"{llm['confidence_schwelle'].default}; Verwendungszweck und Name gehen "
        f"maskiert hinaus. **Automatisch gebucht** (Status auto) wird ab Confidence "
        f"{schwelle}; darunter geht die Buchung zur Prüfung.",
        "",
    )
    d(
        "Weitere Wege, auf denen accounti ohne menschliche Freigabe bucht (Status "
        "auto; sie gelten wie jede Freigabe und sind nur per Storno korrigierbar):",
        "",
        "- Eingangs- und Ausgangsrechnungen über accounti opos verbuchen — Sachkonto "
        "aus Kontakt oder Regel, sonst zur Prüfung;",
        "- Belegabgleich: Bankumsatz mit passendem Beleg, Konten aus dem Beleg "
        "(classify);",
        "- Zahlungsausgleich offener Posten (opos zuordnen, bank lauf), auch Skonto;",
        "- Kreditkartenabgleich (Sammelabbuchung gegen Einzelbelastungen);",
        "- Marktplatz-Abrechnungen und -Auszahlungen (Amazon, eBay, PayPal …), "
        "Unklares zur Prüfung;",
        "- Zahllast der Umsatzsteuer-Voranmeldung bzw. Sondervorauszahlung nach "
        "erfolgreicher ELSTER-Übermittlung (an das Finanzamt als Kreditor).",
        "",
    )


def _freigabe(d: _Doku) -> None:
    from accounti.aufgaben.einstellungen import lade_aufgaben_einstellungen
    from accounti.zahlung.konfiguration import lade_zahlung

    d("### 2.4 Freigabe, Korrektur und Storno", "")
    d(
        "Ein Vorschlag (Status entwurf, pruefung) wird von einem Menschen freigegeben "
        "(accounti bestaetige) oder direkt korrigiert (accounti korrigiere). Ab der "
        "Freigabe (auto, geprueft, korrigiert, exportiert) ist eine Buchung "
        "unveränderbar: Korrekturen sind eine Stornobuchung (Soll/Haben getauscht) "
        "mit Neubuchung, beide verweisen aufeinander; die Datenbankschicht lehnt "
        "jede andere Änderung und jedes Löschen ab. Jede Freigabe, Korrektur, jedes "
        "Storno und jeder Export steht im Journal.",
        "",
    )
    aufgaben = d.lade(lade_aufgaben_einstellungen, "aufgaben")
    if aufgaben is not None:
        rollen = [[r, ", ".join(w)] for r, w in sorted(aufgaben.rollen.items())]
        d("Rollen (bis zur Benutzerverwaltung als Namen):", "")
        d(*_tabelle(["Rolle", "Personen"], rollen))
        d(
            f"Zuständigkeitsregeln: {len(aufgaben.zustaendigkeit)}; Erinnerungsstufen "
            f"{aufgaben.erinnerung.stufen} Tage nach Fälligkeit"
            + (
                f", Eskalation an {aufgaben.erinnerung.eskalation_an}"
                if aufgaben.erinnerung.eskalation_an
                else ""
            )
            + ".",
            "",
        )
    zahlung = d.lade(lade_zahlung, "zahlung")
    if zahlung is not None:
        d(
            f"Zahlungsläufe: Vier-Augen-Prinzip {_ja(zahlung.vier_augen)}"
            + (
                f", freigeben dürfen {', '.join(zahlung.freigeber)}"
                if zahlung.freigeber
                else ""
            )
            + "; Freigabe als Zustand mit Freigabe-Hash, SEPA-Datei (pain.001) "
            "byte-gleich gespeichert.",
            "",
        )


def _pruefung(d: _Doku) -> None:
    from accounti.aufgaben.prueflaeufe import PRUEFLAEUFE
    from accounti.pruefung.einstellungen import lade_pruefung
    from accounti.pruefung.regeln import PRUEFREGELN, _lade_regeln

    d("### 2.5 Prüfregeln und Nachforderung", "")
    e = d.lade(lade_pruefung, "pruefung")
    if e is None:
        return
    _lade_regeln()
    zeilen: list[list[object]] = []
    for name, r in sorted(
        PRUEFREGELN.items(), key=lambda x: (x[1].kategorie.value, x[0])
    ):
        try:
            p = r.Parameter.model_validate(e.regeln.get(name, {}))
            schwellen = schwellen_text(p.model_dump(mode="json"))
        except ValueError:
            schwellen = "fehlerhaft"
        zeilen.append(
            [
                name,
                r.kategorie.value,
                e.schwere.get(name, r.schwere).value,
                "abgeschaltet" if name in e.abgeschaltet else "aktiv",
                schwellen or "—",
            ]
        )
    d(*_tabelle(["Regel", "Kategorie", "Schwere", "Stand", "Schwellen"], zeilen))
    d(
        f"Kleinbetragsrechnung bis {e.kleinbetrag_grenze} € (§ 33 UStDV). "
        "Begründet belegfreie Umsätze:",
        "",
    )
    d(
        *_tabelle(
            ["Regel", "Muster", "Feld", "Begründung"],
            [[r.name, r.muster, r.feld, r.begruendung] for r in e.belegfrei],
        )
    )
    d(
        "Fehlt ein Beleg, entsteht eine Aufgabe „Beleg fehlt“ (accounti nachfordern, "
        "Prüfläufe: " + ", ".join(sorted(PRUEFLAEUFE)) + "), die sich schließt, "
        "sobald der Beleg abgeglichen ist. Anfragen an Lieferanten verschickt "
        "accounti nur auf ausdrücklichen Befehl je Anfrage.",
        "",
    )


def _perioden(d: _Doku) -> None:
    from accounti.abschluss.konfiguration import gewinnermittlung_angegeben

    ziel = (
        "— bei Einnahmenüberschussrechnung auch im Folgejahr, der Abfluss zählt —"
        if gewinnermittlung_angegeben(d.config) == "euer"
        else "desselben Geschäftsjahres"
    )
    from accounti.db.repo_abschluss import lade_gesperrte_jahre
    from accounti.pruefung.perioden import lade_perioden

    d("### 2.6 Festschreibung und Abschluss", "")
    jahre = sorted(lade_gesperrte_jahre(d.s))
    perioden = lade_perioden(d.s)
    d(
        "Abgeschlossene Geschäftsjahre (Saldovortrag): "
        + (", ".join(str(j) for j in jahre) or "keine")
        + ".",
        "",
    )
    d(
        *_tabelle(
            ["Monat", "Stand", "geschlossen", "zuletzt geöffnet", "Grund"],
            [
                [
                    p.monat,
                    "festgeschrieben" if p.gesperrt else "offen",
                    f"{datum_de(p.geschlossen_am.date())} {p.geschlossen_von}",
                    f"{datum_de(p.geoeffnet_am.date())} {p.geoeffnet_von}"
                    if p.geoeffnet_am
                    else "—",
                    p.grund,
                ]
                for p in perioden
            ],
        )
    )
    d(
        "Ein festgeschriebener Zeitraum nimmt keine Buchung an; geöffnet wird nur mit "
        "Begründung, protokolliert im Abschlussprotokoll und im Journal. Einzige "
        "Ausnahme: Eröffnungsbuchungen (EB-Werte) des Saldovortrags (accounti "
        "abschluss vortrag) und des ersten Eröffnungssaldos — nur neu angelegt, nur "
        "am 01.01., ohne Steuer, Belegnummer EB-JJJJ, eine Seite ein "
        "Saldenvortragskonto. Sie tragen die Schlussbilanz des Vorjahres vor, ändern "
        "weder Verkehrszahlen noch Umsatzsteuer-Voranmeldung des Januars und stehen "
        "wie jede Buchung im Journal; die Sperre des Geschäftsjahres gilt für sie "
        "weiter. Eine Eingangsrechnung zu einem festgeschriebenen Monat wird mit "
        f"accounti opos verbuchen --buchungsdatum in einen offenen Monat {ziel} "
        "gebucht (Vorsteuer nach § 15 Abs. 1 Nr. 1 UStG).",
        "",
    )


def _steuer(d: _Doku) -> None:
    from accounti.elster.konfiguration import lade_elster

    d("### 2.7 Steuer und Export", "")
    elster = d.lade(lade_elster, "elster")
    if elster is not None:
        d(
            f"ELSTER: Übermittler {elster.uebermittler}, eigene Hersteller-ID "
            f"eingerichtet: {_ja(elster.hersteller_id)}; Abgabe nur nach Freigabe "
            "durch einen Menschen, Übermittlungsprotokoll nur anfügbar.",
            "",
        )
    d(
        "DATEV: Buchungsstapel (EXTF) nur aus freigegebenen Buchungen; exportierte "
        "Buchungen werden als exportiert vermerkt, der Export (Datei, SHA-256) steht "
        "im Journal.",
        "",
    )


# --- 3 Technische Systemdokumentation ----------------------------------------------


def _technik(d: _Doku) -> None:
    from accounti.pruefung.journal import lade_journal, pruefe_journal

    d("## 3 Technische Systemdokumentation", "")
    p = pruefe_journal(d.s)
    if p.vorhanden:
        stand = "in Ordnung" if p.in_ordnung else f"{len(p.befunde)} Befunde"
        d(
            f"- **Journal:** {p.anzahl} Einträge, Kopf Nr. {p.kopf_nr} "
            f"(SHA-256 {p.kopf_hash[:16]}…), Prüfung heute: {stand}. Nur anfügbar "
            "(ORM-Sperre"
            + (", SQLite-Trigger" if d.db_url and d.db_url.startswith("sqlite") else "")
            + "), jeder Eintrag per SHA-256 an seinen Vorgänger gekettet; "
            "accounti journal pruefen gleicht zusätzlich Buchungen, Belege und "
            "Sperren mit dem Journal ab.",
        )
        vorgaenge: dict[str, int] = {}
        for e in lade_journal(d.s):
            vorgaenge[e.vorgang] = vorgaenge.get(e.vorgang, 0) + 1
        d(
            "- **Vorgänge im Journal:** "
            + (", ".join(f"{k} {v}" for k, v in sorted(vorgaenge.items())) or "keine"),
        )
    else:
        d("- **Journal:** in dieser Datenbank nicht angelegt.")
    d(
        "- **Weitere Protokolle mit Hash-Kette:** USt-IdNr.-Bestätigungen, "
        "Abschlussprotokoll, Steuermeldungen, festgeschriebene Kontoauszüge; "
        "Zahlungslauf- und Aufgabenverlauf nur anfügbar.",
        f"- **Verschlüsselung:** Bank- und Kanalzugänge, Zertifikats-PIN mit AES-GCM; "
        "Schlüssel ACCOUNTI_SCHLUESSEL gesetzt: "
        f"{_ja(os.environ.get('ACCOUNTI_SCHLUESSEL'))}.",
        "- **Datenschutz:** LLM-Anfragen enthalten nur maskierte Daten; OCR lokal.",
        "",
    )


# --- 4 Betriebsdokumentation ----------------------------------------------------


def _betrieb(d: _Doku, archiv: Path | None, vorgaenger: list[Journaleintrag]) -> None:
    from accounti.db.tabellen import BelegRow

    d("## 4 Betriebsdokumentation", "")
    bis = d.s.execute(
        select(func.min(BelegRow.aufbewahren_bis), func.max(BelegRow.aufbewahren_bis))
    ).one()
    d(
        f"- **Belegarchiv:** {_zelle(archiv) if archiv else 'nicht angegeben'}; "
        f"Aufbewahrungsfristen im Bestand {datum_de(bis[0])} bis {datum_de(bis[1])}.",
        "- **Datensicherung:** nicht Teil von accounti — Verfahren, Turnus und "
        "Aufbewahrungsort der Sicherungen legt der Betrieb fest und ergänzt sie hier.",
        "- **Geplante Läufe:** aus dem System nicht ablesbar (Cron/Timer des "
        "Betriebs, z.B. accounti bank lauf && accounti aufgaben lauf).",
        "",
        "### Änderungshistorie dieser Dokumentation",
        "",
    )
    d(
        *_tabelle(
            ["Journal-Nr.", "Datum", "Person", "Fassung (SHA-256)"],
            [
                [e.nr, datum_de(e.zeitpunkt.date()), e.person, (e.bezug or "")[:16]]
                for e in vorgaenger
            ],
        )
    )


def erzeuge(
    session: Session,
    config: str | Path = STANDARD_PFAD,
    *,
    db_url: str | None = None,
    archiv: str | Path | None = None,
    stand: date | None = None,
) -> str:
    """Die Verfahrensdokumentation als Markdown — aus dem Systemzustand."""
    from accounti.pruefung.journal import lade_journal

    d = _Doku(session, Path(config), db_url)
    stand = stand or date.today()
    name = (d.roh().get("mandant") or {}).get("name") or "nicht eingerichtet"
    d(
        f"# Verfahrensdokumentation — {_zelle(name)}",
        "",
        f"Stand: {datum_de(stand)} · erzeugt von accounti {__version__} aus dem "
        f"eingerichteten System (Konfiguration {_zelle(config)}). Gliederung nach "
        "GoBD Rz. 151 ff.; Abschnitte ohne Angabe bitte vom Betrieb ergänzen.",
        "",
    )
    _allgemein(d)
    d("## 2 Anwenderdokumentation", "")
    for abschnitt in (
        _belegeingang,
        _bank,
        _kontierung,
        _freigabe,
        _pruefung,
        _perioden,
        _steuer,
    ):
        abschnitt(d)
    _technik(d)
    vorgaenger = lade_journal(session, vorgang=VORGANG)
    _betrieb(d, Path(archiv) if archiv else None, vorgaenger)
    return "\n".join(d.zeilen).rstrip() + "\n"


def fassung(markdown: str) -> str:
    return hashlib.sha256(markdown.encode("utf-8")).hexdigest()


def vermerke(
    session: Session, markdown: str, datei: str | None
) -> Journaleintrag | None:
    """Die erzeugte Fassung ins Journal (Änderungshistorie, GoBD Rz. 154)."""
    from accounti.pruefung.journal import schreibe

    hash_ = fassung(markdown)
    return schreibe(
        session,
        VORGANG,
        "verfahrensdoku",
        hash_[:16],
        nachher={"datei": datei, "sha256": hash_, "zeilen": markdown.count("\n")},
        bezug=hash_,
    )


def als_pdf(markdown: str, ziel: str | Path) -> Path:
    """Einfache PDF-Fassung (fpdf2, Liberation Sans wie E-Rechnung und Mahnung)."""
    from fpdf import FPDF

    schriften = Path(__file__).resolve().parent.parent / "erechnung" / "schriften"
    pdf = FPDF(format="A4")
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_font("Sans", "", str(schriften / "LiberationSans-Regular.ttf"))
    pdf.add_font("Sans", "B", str(schriften / "LiberationSans-Bold.ttf"))
    pdf.add_page()
    breite = pdf.w - pdf.l_margin - pdf.r_margin
    for zeile in markdown.splitlines():
        text = zeile.replace("**", "").replace("_(keine)_", "(keine)")
        if zeile.startswith("# "):
            pdf.set_font("Sans", "B", 15)
            pdf.multi_cell(breite, 8, text[2:])
        elif zeile.startswith("## "):
            pdf.set_font("Sans", "B", 12)
            pdf.ln(2)
            pdf.multi_cell(breite, 7, text[3:])
        elif zeile.startswith("### "):
            pdf.set_font("Sans", "B", 10)
            pdf.multi_cell(breite, 6, text[4:])
        elif zeile.startswith("|---") or zeile.startswith("|-"):
            continue
        elif zeile.startswith("|"):
            pdf.set_font("Sans", "", 8)
            zellen = [z.strip() for z in zeile.strip("|").split("|")]
            pdf.multi_cell(breite, 4.5, "  ·  ".join(zellen))
        elif zeile.startswith("- "):
            pdf.set_font("Sans", "", 9)
            pdf.multi_cell(breite, 5, "• " + text[2:])
        elif zeile.strip():
            pdf.set_font("Sans", "", 9)
            pdf.multi_cell(breite, 5, text.lstrip("> "))
        else:
            pdf.ln(2)
    ziel = Path(ziel)
    pdf.output(str(ziel))
    return ziel
