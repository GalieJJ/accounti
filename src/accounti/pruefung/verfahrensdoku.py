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
import re
import shutil
from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import yaml
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from accounti import __version__
from accounti.anzeige import datum_de
from accounti.konfiguration import STANDARD_PFAD, KonfigurationError
from accounti.models.pruefung import Journaleintrag

VORGANG = "verfahrensdoku_erstellt"


def _zelle(wert: object) -> str:
    """Tabellenzelle: ``|`` maskiert (``\\|``) statt ersetzt — ein Regelmuster
    ``A|B`` muss so dokumentiert sein, wie es gilt (GoBD Rz. 151 ff.)."""
    if wert is None:
        return "—"
    return str(wert).replace("|", "\\|").replace("\n", " ")


def _zellen(zeile: str) -> list[str]:
    """Zellen einer Markdown-Tabellenzeile; ``\\|`` ist ein Zeichen, kein Trenner."""
    teile = re.split(r"(?<!\\)\|", zeile.strip().removeprefix("|").removesuffix("|"))
    return [z.strip().replace("\\|", "|") for z in teile]


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
    def __init__(
        self,
        session: Session,
        config: Path,
        db_url: str | None,
        system_db: str | None = None,
        gesellschaft: str | None = None,
    ) -> None:
        self.s = session
        self.config = config
        self.db_url = db_url
        self.system_db = system_db
        self.gesellschaft = gesellschaft
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
    from accounti.abschluss.konfiguration import (
        gewinnermittlung_angegeben,
        lade_abschluss,
    )
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
        if gewinnermittlung_angegeben(d.config) is None:
            # wie 2.6: ohne Angabe schützt accounti den Jahreswechsel wie bei Bilanz
            art += (
                " (Standard, nicht ausdrücklich angegeben — ein Buchungsdatum im "
                "Folgejahr lehnt accounti deshalb ab)"
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
    from accounti.belege.kanaele.einstellungen import lade_belegkanaele
    from accounti.belege.llm import LLMBelegEngine
    from accounti.betrieb.aufbewahrung import Unterlage, frist

    d("### 2.1 Belegeingang und Erkennung", "")
    kanaele = d.lade(lade_belegkanaele, "belegkanaele")
    d("Eingerichtete Kanäle (Ordner und Upload stehen immer zur Verfügung):", "")
    if kanaele is not None:
        zeilen: list[list[object]] = [
            ["ordner", "—", "accounti belege abholen --kanal ordner"],
            ["upload", "—", "accounti belege import (Handimport einzelner Dateien)"],
        ]
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
            "Dateiprüfung für E-Mail, Webhook, Connector und Ordner: höchstens "
            f"{kanaele.max_groesse_mb} MB, Typen {', '.join(kanaele.dateitypen)} (Typ "
            "am Inhalt geprüft); abgelehnte Dateien werden gemeldet, im Ordner nach "
            "abgelehnt/ verschoben und nicht archiviert. Der Handimport einzelner "
            "Dateien (accounti belege import) prüft Typ und Größe nicht — die Datei "
            "wählt der Anwender selbst.",
            "",
        )
    llm = inspect.signature(LLMBelegEngine).parameters["model"].default
    beleg, rechnung, buch = (
        frist(u) for u in (Unterlage.BUCHUNGSBELEG, Unterlage.RECHNUNG, Unterlage.BUCH)
    )
    d(
        "Erkennung: strukturierte E-Rechnung (XRechnung, ZUGFeRD) vor Textebene, "
        "Textebene vor OCR. OCR lokal mit Tesseract "
        f"({'installiert' if shutil.which('tesseract') else 'nicht installiert'}). "
        f"Eine LLM-Stufe ({llm}) läuft nur auf ausdrücklichen Wunsch (--llm) und "
        "erhält den Belegtext maskiert (IBAN, USt-IdNr., Namen, Nummern).",
        "",
        "Archiv: Originaldateien unverändert, unter ihrem SHA-256 abgelegt, "
        "schreibgeschützt, ohne Löschpfad; Aufbewahrung der Buchungsbelege "
        f"{beleg.jahre} Jahre ({beleg.grundlage}), Rechnungen {rechnung.jahre} Jahre "
        f"({rechnung.grundlage}), jeweils ab Schluss des Kalenderjahres des "
        "Belegdatums, ohne Belegdatum des Eingangs (§ 147 Abs. 4 AO, § 14b Abs. 1 "
        f"Satz 3 UStG); Bücher und Aufzeichnungen {buch.jahre} Jahre ({buch.grundlage}"
        ", accounti betrieb aufbewahrung). Dubletten werden über Datei-Hash, "
        "Lieferant und Nummer, Betrag und Datum erkannt und verworfen bzw. zur "
        "Prüfung vorgelegt.",
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
    from accounti.klassifikation.engine import standard_regeln
    from accounti.klassifikation.llm import LLMEngine
    from accounti.klassifikation.regeln_loader import lade_regeln
    from accounti.konfiguration import Buchhaltung, lade_buchhaltung

    d("### 2.3 Kontierung", "")
    regeln_datei = Path("config/regeln.yaml")  # wie classify: im Arbeitsverzeichnis
    try:
        eigene = lade_regeln(regeln_datei) if regeln_datei.is_file() else []
    except KonfigurationError as fehler:
        d(f"> **Regeldatei fehlerhaft:** {_zelle(fehler)}", "")
        eigene = []
    try:
        buchhaltung = lade_buchhaltung(d.config)
    except (KonfigurationError, ValueError):
        buchhaltung = Buchhaltung()  # der Fehler steht schon in Abschnitt 1
    standard = standard_regeln(buchhaltung.kontenrahmen, buchhaltung.bank_konto)
    schwelle = inspect.signature(zu_buchungssatz).parameters["auto_schwelle"].default
    llm = inspect.signature(LLMEngine).parameters
    d(
        f"Reihenfolge: Beleg (Belegabgleich, offene Posten) → Regelwerk → LLM. "
        f"Regelwerk: {len(eigene)} eigene Regeln ({_zelle(regeln_datei)}) vor "
        f"{len(standard)} Standardregeln im Kontenrahmen {buchhaltung.kontenrahmen}.",
        "",
    )
    if eigene:
        d(
            *_tabelle(
                [
                    "Regel",
                    "Muster",
                    "Feld",
                    "Richtung",
                    "Soll",
                    "Haben",
                    "Schlüssel",
                    "Prüfen",
                ],
                [
                    [
                        r.name,
                        r.muster.pattern,
                        r.feld,
                        r.richtung or "beide",
                        r.soll_konto,
                        r.haben_konto,
                        r.steuer_schluessel,
                        _ja(r.pruefen or r.confidence < schwelle),
                    ]
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
        "Immer zur Prüfung, unabhängig von der Confidence: Treffer einer Regel mit "
        "`pruefen` (z. B. Miete, § 4 Nr. 12/§ 9 UStG; § 13b-Leistungen); ein Umsatz "
        "gegen die Richtung einer Regel (Erstattung auf eine Ausgaberegel) als "
        "Gegenbuchung mit getauschtem Soll/Haben (§ 17 Abs. 1 UStG); jeder Vorschlag "
        "— auch aus gelernten Regeln und dem LLM — mit dem Bankkonto auf der falschen "
        "oder auf keiner Seite. Marktplatz-Auszahlungen (Stichworte "
        "`integrationen.marktplaetze.<name>.bank_stichworte`, offene Auszahlungen "
        "importierter Abrechnungen) bucht die Kontierung nicht: Sie bleiben offen, "
        "bis der Abgleich mit der Abrechnung sie gegen das Verrechnungskonto bucht.",
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
        d("Zuständigkeitsrollen der Aufgaben (Namen):", "")
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
    _benutzer(d)


def _benutzerliste(d: _Doku) -> list[list[object]] | None:
    """Benutzer mit ihren Rollen in der aktiven Gesellschaft (sonst allen) aus der
    Systemdatenbank — ``None``: keine Benutzer oder Systemdatenbank nicht lesbar.
    Eine SQLite-Systemdatenbank, die es nicht gibt, wird nicht angelegt."""
    from sqlalchemy import inspect as sql_inspect
    from sqlalchemy import make_url

    from accounti.db import session_factory
    from accounti.db.repo_auth import lade_alle_benutzer, rollen_von

    def lies(s: Session) -> list[list[object]] | None:
        if not sql_inspect(s.get_bind()).has_table("auth_benutzer"):
            return None
        alle = lade_alle_benutzer(s)
        zeilen: list[list[object]] = []
        for b in alle:
            rollen = [
                r
                for r in rollen_von(s, b.id)
                if d.gesellschaft is None or r.gesellschaft == d.gesellschaft
            ]
            if d.gesellschaft is not None and not rollen:
                continue  # Benutzer anderer Gesellschaften gehören nicht hierher
            text = sorted(f"{r.rolle.value} ({r.gesellschaft})" for r in rollen)
            zeilen.append(
                [b.name, ", ".join(text) or "—", _ja(b.totp_aktiv), _ja(b.aktiv)]
            )
        return zeilen if alle else None

    if d.system_db is None or d.system_db == d.db_url:
        return lies(d.s)
    url = make_url(d.system_db)
    datei = url.database or ""
    if (
        url.get_backend_name() == "sqlite"
        and datei not in ("", ":memory:")
        and not datei.startswith("file:")
        and not Path(datei).is_file()
    ):
        return None
    engine, fabrik = session_factory(d.system_db)
    try:
        with fabrik() as s:
            return lies(s)
    except SQLAlchemyError:
        return None
    finally:
        engine.dispose()


def _benutzer(d: _Doku) -> None:
    from accounti.models.auth import FREIGABEWEGE, RECHT_TEXT, ROLLEN_RECHTE, Recht
    from accounti.pruefung.journal import benutzer_eingerichtet

    benutzer = _benutzerliste(d)
    if benutzer is None and not benutzer_eingerichtet(d.s.connection()):
        d(
            "Benutzer und Rechte: keine Benutzer eingerichtet — accounti prüft keine "
            "Rollen; die handelnde Person ist ein Freitext (--von, ACCOUNTI_BENUTZER, "
            "sonst der Anmeldename) und steht so im Journal.",
            "",
        )
        return
    if benutzer is None:  # gebunden, aber die Systemdatenbank fehlt oder ist leer
        d(
            "Benutzer und Rechte: Die Datenbank gehört zu einer Benutzerverwaltung "
            "(Bindung an eine Systemdatenbank), deren Benutzerliste hier nicht lesbar "
            "ist — ACCOUNTI_SYSTEM_DB bzw. gesellschaften.systemdatenbank prüfen. "
            "Rollen und Einmalcode gelten trotzdem:",
            "",
        )
    else:
        wo = f" in der Gesellschaft {d.gesellschaft}" if d.gesellschaft else ""
        d(
            f"Benutzer und Rechte: {len(benutzer)} Benutzer mit Rolle{wo} (Anmeldung "
            "mit Passwort und zweitem Faktor, Rollen je Gesellschaft):",
            "",
        )
        d(*_tabelle(["Benutzer", "Rollen", "zweiter Faktor", "aktiv"], benutzer))
    d(
        "Rechte je Rolle: "
        + " · ".join(
            f"{rolle.value}: "
            + ", ".join(RECHT_TEXT[r] for r in sorted(rechte, key=list(Recht).index))
            for rolle, rechte in ROLLEN_RECHTE.items()
        )
        + ". Die Rollen sind nicht hierarchisch — wer bucht, gibt keine Zahlungen "
        "frei und öffnet keinen festgeschriebenen Zeitraum.",
        "",
        "Jeder der folgenden Befehle verlangt in der CLI Rolle und Einmalcode (TOTP "
        "oder Wiederherstellungscode); im Browser verlangt jede Freigabe einen "
        "frischen Einmalcode. Im Journal, in geprueft_von und in den Protokollen "
        "steht der Benutzer; Personen, die keine Rechteprüfung bestätigt hat "
        "(Läufe, Importe), stehen als „(ungeprüft)“ im Journal, API-Token als "
        "„API-Token <Name>“.",
        "",
    )
    d(
        *_tabelle(
            ["Recht", "Befehle (accounti …)"],
            [
                [RECHT_TEXT[recht], ", ".join(befehle)]
                for recht, befehle in FREIGABEWEGE.items()
            ],
        )
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
        "Saldenvortragskonto, die andere ein Bestandskonto, kein Storno. Sie "
        "tragen die Schlussbilanz des Vorjahres vor, ändern "
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
    sicherungsschluessel = os.environ.get(
        "ACCOUNTI_SICHERUNG_SCHLUESSEL"
    ) or os.environ.get("ACCOUNTI_SCHLUESSEL")
    bis = d.s.execute(
        select(func.min(BelegRow.aufbewahren_bis), func.max(BelegRow.aufbewahren_bis))
    ).one()
    d(
        f"- **Belegarchiv:** {_zelle(archiv) if archiv else 'nicht angegeben'}; "
        f"Aufbewahrungsfristen im Bestand {datum_de(bis[0])} bis {datum_de(bis[1])}.",
        "- **Datensicherung:** accounti sicherung erstellen sichert Datenbank und "
        "Belegarchiv in einer Datei, verschlüsselt (AES-256-GCM, Schlüssel "
        "ACCOUNTI_SICHERUNG_SCHLUESSEL bzw. ACCOUNTI_SCHLUESSEL, gesetzt: "
        f"{_ja(sicherungsschluessel)}); accounti sicherung pruefen prüft jede Datei "
        "gegen ihr Manifest, wiederhergestellt wird nur in eine leere Umgebung. "
        "Turnus, Aufbewahrungsort und Wiederherstellungstests legt der Betrieb fest "
        "und ergänzt sie hier.",
        "- **Geplante Läufe:** accounti betrieb lauf (im Docker-Setup der Dienst "
        "lauf) startet je Gesellschaft im Intervall accounti bank lauf und accounti "
        "aufgaben lauf; ohne ihn Cron/Timer des Betriebs. Laufsperre: je Datenbank "
        "läuft jede Art höchstens einmal zugleich — bank (bank lauf und seine "
        "Schritte, classify, opos zuordnen, bank abgleich, opos verbuchen, periode "
        "schliessen) und aufgaben (aufgaben lauf, nachfordern); ein zweiter Lauf "
        "wartet nicht, er endet mit einer Meldung.",
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
    system_db: str | None = None,
    gesellschaft: str | None = None,
) -> str:
    """Die Verfahrensdokumentation als Markdown — aus dem Systemzustand.

    ``system_db``: Datenbank mit Benutzern und Rollen (Registry bzw.
    ``ACCOUNTI_SYSTEM_DB``); ohne Angabe die Datenbank der Sitzung.
    ``gesellschaft``: nur Benutzer mit Rollen in dieser Gesellschaft."""
    from accounti.pruefung.journal import lade_journal

    d = _Doku(session, Path(config), db_url, system_db, gesellschaft)
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
            zellen = _zellen(zeile)
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
