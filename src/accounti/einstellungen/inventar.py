"""Inventar der Einstellungen als Daten (Baustein 10c P4, Spec Anhang A).

Hier steht, welche Abschnitte es gibt und wohin sie gehören (Datenbank, nur Datei,
nur Datenbank), welche Felder Betriebswerte sind (immer aus der Datei, D7), welche
Geheimnisse (D8), Periodenwerte (D14), Kontofelder und meldepflichtigen Felder (A60)
es gibt, welches Modell einen Abschnitt prüft und welcher Lader welche Abschnitte
liest (auch mittelbar).

Keine Importe aus Fachmodulen: Modelle und Lader stehen als Punktnamen da und werden
erst dort aufgelöst, wo sie gebraucht werden (``einstellungen/pruefung.py``, Tests).

**Pfade** sind Punktpfade mit den Schlüsseln der Datei (Alias, nicht Feldname): eine
Betriebsfeld-Angabe deckt den ganzen Teilbaum darunter (``elster.eric``); ``[]``
steht für jedes Element einer Liste von Zuordnungen, die über ihren ``name``
zugeordnet werden (``belegkanaele.email[].ca_datei``).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Annotated, Literal, TypeVar
from urllib.parse import urlsplit

from pydantic import Field

T = TypeVar("T")

# Markierung am Modellfeld: ein Betriebswert (Pfad, Host, Port …) — Quelle der Wahrheit
# für BETRIEBSFELDER (Strukturtest tests/test_einstellungen_inventar.py)
BETRIEB = {"accounti": "betrieb"}
Betriebsfeld = Annotated[T, Field(json_schema_extra=BETRIEB)]

Ziel = Literal["db", "datei", "nur_db"]


@dataclass(frozen=True)
class AbschnittInfo:
    """``ziel``: ``db`` (Datenbank vor Datei), ``datei`` (Betrieb, nur Datei/Umgebung),
    ``nur_db`` (nie aus der Datei). ``unvollstaendig_erlaubt``: Fehlerarten, die eine
    Version als „fehlt noch“ (``vollstaendig=false``) speichern lässt (D16, M5)."""

    ziel: Ziel = "db"
    schema_version: int = 1
    unvollstaendig_erlaubt: frozenset[str] = frozenset()


ABSCHNITTE: dict[str, AbschnittInfo] = {
    "mandant": AbschnittInfo(
        unvollstaendig_erlaubt=frozenset({"missing", "pflicht_fehlt"})
    ),
    "buchhaltung": AbschnittInfo(),
    "datev": AbschnittInfo(),
    "abschluss": AbschnittInfo(),
    "kasse": AbschnittInfo(),
    "anlagen": AbschnittInfo(),
    "elster": AbschnittInfo(),
    "ustid_pruefung": AbschnittInfo(),
    "bank": AbschnittInfo(),
    "import": AbschnittInfo(),
    "zahlung": AbschnittInfo(),
    "mahnwesen": AbschnittInfo(),
    "belegkanaele": AbschnittInfo(),
    "integrationen": AbschnittInfo(),
    "llm": AbschnittInfo(),
    "pruefung": AbschnittInfo(),
    "aufgaben": AbschnittInfo(),
    "versand": AbschnittInfo(),
    "bwa": AbschnittInfo(),  # Baustein 10b-2
    "einrichtung": AbschnittInfo(ziel="nur_db"),  # P7: ausgeblendete Punkte
    # Betrieb: nur Datei bzw. Umgebung (A42)
    "database": AbschnittInfo(ziel="datei"),
    "server": AbschnittInfo(ziel="datei"),
    "auth": AbschnittInfo(ziel="datei"),
    "gesellschaften": AbschnittInfo(ziel="datei"),
    "einstellungen": AbschnittInfo(ziel="datei"),  # quelle, festgelegt (E2)
}
# ein Abschnitt, den das Inventar (noch) nicht kennt, gilt als Datenbank-Abschnitt —
# so greift auch für ihn der fail-closed-Weg im Web (D5)
UNBEKANNT = AbschnittInfo()
BETRIEBSABSCHNITTE = frozenset(n for n, i in ABSCHNITTE.items() if i.ziel == "datei")

# Betriebswerte in Datenbank-Abschnitten (A42, D7): beim Lesen immer aus der Datei, beim
# Schreiben abgewiesen; je Eintrag markiert das Modellfeld sie mit Betriebsfeld[...]
BETRIEBSFELDER = frozenset(
    {
        "elster.eric",  # ERiC: Bibliothek, Plugins, Log, Zertifikat, PIN-Datei
        "pruefung.archiv",
        "pruefung.kontenrahmen_datei",
        "belegkanaele.webhook.host",
        "belegkanaele.webhook.port",
        "belegkanaele.email[].ca_datei",
        "ustid_pruefung.url",
        "bank.fints.produkt_id",
        "abschluss.kontenzuordnung",
        "anlagen.rechtsstand",
    }
)
# Felder, die nach Pfad aussehen (Typ Path oder Name mit datei|pfad|archiv|…), aber
# keine Betriebswerte sind — je mit Grund
KEIN_BETRIEBSFELD: dict[str, str] = {
    "belegkanaele.dateitypen": "erlaubte Dateitypen, kein Pfad",
    "belegkanaele.email[].ordner": "IMAP-Ordner im Postfach, kein Dateipfad",
    "belegkanaele.email[].ziel_ordner": "IMAP-Ordner im Postfach, kein Dateipfad",
    "belegkanaele.webhook.max_dateien": "Anzahl je Anfrage, kein Pfad",
    "belegkanaele.connectoren[json].liste.pfad": "URL-Pfad im Portal, keine Datei",
    "belegkanaele.connectoren[json].felder.dateiname": "Feldname in der JSON-Antwort",
    "belegkanaele.connectoren[json].datei": "Abruf der Datei im Portal (URL-Pfad)",
    "belegkanaele.connectoren[json].datei.pfad": "URL-Pfad im Portal, keine Datei",
}


def _url(wert: str) -> str | None:
    teile = urlsplit(wert)
    if teile.scheme not in ("http", "https") or not teile.hostname:
        return "http(s)-Adresse erwartet"
    return None


def _nicht_leer(wert: str) -> str | None:
    return None if wert.strip() else "darf nicht leer sein"


@dataclass(frozen=True)
class Geheimfeld:
    """``verbrauch``: die eine Stelle, die den Wert liest (``modul:name``);
    ``pruefe``: Formprüfung des Werts (Fehlertext oder ``None``)."""

    verbrauch: str
    pruefe: Callable[[str], str | None]


# Geheimnisse (D8): nie in einem Modell, gelesen nur an den Verbrauchsstellen
GEHEIMFELDER: dict[str, Geheimfeld] = {
    "versand.smtp.passwort": Geheimfeld(
        "accounti.erechnung.versand:SmtpVersand", _nicht_leer
    ),
    "llm.api_key": Geheimfeld("accounti.klassifikation.llm:LLMEngine", _nicht_leer),
    "aufgaben.benachrichtigung.webhook.url": Geheimfeld(
        "accounti.aufgaben.benachrichtigung:_webhook_aus_konfiguration", _url
    ),
    "elster.pin": Geheimfeld(
        "accounti.elster.uebermittlung:waehle_uebermittler", _nicht_leer
    ),
}

# Periodenwerte „ab Zeitraum → Wert“ (E3, D14)
PERIODENFELDER: dict[str, Literal["jahr", "quartal", "wirtschaftsjahr"]] = {
    "elster.voranmeldungszeitraum": "jahr",
    "elster.dauerfristverlaengerung": "jahr",
    "mandant.oss": "quartal",
    "abschluss.gewinnermittlung": "wirtschaftsjahr",
}

# Kontofelder für die Querprüfungen (D16): ``*`` = jeder Wert einer Zuordnung,
# ``[]`` = jedes Listenelement
Kontoart = Literal["sachkonto", "bankkonto", "erfolgskonto"]
KONTOFELDER: dict[str, Kontoart] = {
    "buchhaltung.bank_konto": "bankkonto",
    "buchhaltung.standard_aufwand": "erfolgskonto",
    "buchhaltung.skonto_erhalten.*": "erfolgskonto",
    "buchhaltung.skonto_gewaehrt.*": "erfolgskonto",
    "abschluss.ergebnis_konto": "sachkonto",
    "abschluss.arap_konto": "sachkonto",
    "abschluss.prap_konto": "sachkonto",
    "abschluss.verrechnungskonten[]": "sachkonto",
    "kasse.konto": "sachkonto",
    "anlagen.konten.*": "sachkonto",
    "bank.kreditkarte.geldtransit_konto": "sachkonto",
    "integrationen.geldtransit_konto": "sachkonto",
    "integrationen.erloes_inland.*": "erfolgskonto",
    "integrationen.erloes_ig_lieferung": "erfolgskonto",
    "integrationen.erloes_ausfuhr": "erfolgskonto",
    "integrationen.erloes_unbekannt": "erfolgskonto",
    "integrationen.oss_erloes_konten.*": "erfolgskonto",
    "integrationen.oss_erloes_ermaessigt.*": "erfolgskonto",
    "elster.konto_vorauszahlung": "sachkonto",
    "elster.konto_sondervorauszahlung": "sachkonto",
}

# Änderungen, die alle Verwalter und Freigeber sofort erfahren (A60, Seite in P5)
MELDEPFLICHTIG = frozenset(
    {
        "mandant.bank",
        "elster.finanzamt.iban",
        "zahlung.auftraggeber",
        "zahlung.vier_augen",
        "zahlung.ersteller_darf_freigeben",
        "zahlung.freigeber",
        "zahlung.hoechstbetrag",
        "zahlung.hoechstbetrag_zahlung",
    }
)

# Abschnitt → Modell (Punktname, D16/M4); ``belegkanaele.connectoren[<typ>]`` prüft der
# Typ des Connectors. ``datev``, ``import``, ``llm`` und ``einrichtung`` bekommen ihr
# Modell in Schritt 5, ``bwa`` mit 10b-2.
MODELL: dict[str, str] = {
    "mandant": "accounti.konfiguration.Firma",
    "buchhaltung": "accounti.konfiguration.Buchhaltung",
    "ustid_pruefung": "accounti.konfiguration.UstIdEinstellungen",
    "abschluss": "accounti.abschluss.konfiguration.AbschlussEinstellungen",
    "kasse": "accounti.abschluss.konfiguration.KassenEinstellungen",
    "anlagen": "accounti.anlagen.konfiguration.AnlagenEinstellungen",
    "elster": "accounti.elster.konfiguration.ElsterEinstellungen",
    "bank": "accounti.bank.einstellungen.BankEinstellungen",
    "zahlung": "accounti.zahlung.konfiguration.ZahlungEinstellungen",
    "mahnwesen": "accounti.mahnwesen.konfiguration.MahnEinstellungen",
    "belegkanaele": "accounti.belege.kanaele.einstellungen.KanalEinstellungen",
    "belegkanaele.connectoren[json]": (
        "accounti.belege.kanaele.json_http.JsonEinstellungen"
    ),
    "integrationen": "accounti.integrationen.einstellungen.Integrationen",
    "pruefung": "accounti.pruefung.einstellungen.PruefEinstellungen",
    "aufgaben": "accounti.aufgaben.einstellungen.AufgabenEinstellungen",
    "versand": "accounti.erechnung.versand.VersandKonfiguration",
    "server": "accounti.api.einstellungen.ServerEinstellungen",
    "auth": "accounti.auth.einstellungen.AuthEinstellungen",
    "gesellschaften": "accounti.betrieb.gesellschaften.Gesellschaften",
}

# ältere Stelle → neue Stelle (D16, G-M2): wird beim ersten Speichern umgezogen
UMZUG = {"mandant.kontenrahmen": "buchhaltung.kontenrahmen"}

# Lader (Punktname) → gelesene Abschnitte, auch mittelbar (über andere Lader): jede
# Funktion, die lies_abschnitt aufruft (tests/test_lader_umbau.py, statisch und unter
# einem aufzeichnenden Stand). Die Validierung (P4b) führt je geändertem Abschnitt jeden
# Lader aus, der ihn liest (D16).
_MANDANT_BUCHHALTUNG = frozenset({"buchhaltung", "mandant"})
_INTEGRATIONEN = frozenset({"integrationen", *_MANDANT_BUCHHALTUNG})
LADER: dict[str, frozenset[str]] = {
    "accounti.konfiguration.lade_firma": frozenset({"mandant"}),
    "accounti.konfiguration.lade_buchhaltung": _MANDANT_BUCHHALTUNG,
    "accounti.konfiguration.lade_ustid_pruefung": frozenset({"ustid_pruefung"}),
    "accounti.konfiguration.lade_eigene_firma": frozenset({"mandant"}),
    "accounti.abschluss.konfiguration.lade_wirtschaftsjahr_beginn": frozenset(
        {"datev"}
    ),
    "accounti.abschluss.konfiguration.lade_abschluss": frozenset(
        {"abschluss", "datev", *_INTEGRATIONEN}
    ),
    "accounti.abschluss.konfiguration.gewinnermittlung_angegeben": frozenset(
        {"abschluss"}
    ),
    "accounti.abschluss.konfiguration.lade_kasse": frozenset(
        {"kasse", *_MANDANT_BUCHHALTUNG}
    ),
    "accounti.aufgaben.einstellungen.lade_aufgaben_einstellungen": frozenset(
        {"aufgaben"}
    ),
    "accounti.erechnung.versand.lade_versand": frozenset({"versand"}),
    "accounti.mahnwesen.konfiguration.lade_mahnwesen": frozenset({"mahnwesen"}),
    "accounti.pruefung.einstellungen.lade_pruefung": frozenset({"pruefung"}),
    "accounti.belege.kanaele.einstellungen.lade_belegkanaele": frozenset(
        {"belegkanaele"}
    ),
    "accounti.anlagen.konfiguration.lade_anlagen": frozenset(
        {"anlagen", "datev", *_MANDANT_BUCHHALTUNG}
    ),
    "accounti.elster.konfiguration.lade_elster": frozenset({"elster", *_INTEGRATIONEN}),
    "accounti.elster.konfiguration.lade_elster_konten": frozenset(
        {"elster", *_INTEGRATIONEN}
    ),
    "accounti.elster.konfiguration.lade_oss": frozenset({"mandant"}),
    "accounti.elster.konfiguration.lade_mandant": frozenset({"mandant"}),
    "accounti.integrationen.einstellungen.lade_integrationen": _INTEGRATIONEN,
    "accounti.integrationen.einstellungen.lade_steuerangaben": frozenset({"mandant"}),
    "accounti.bank.einstellungen.lade_bank_einstellungen": frozenset({"bank"}),
    "accounti.zahlung.konfiguration.lade_zahlung": frozenset({"zahlung", "mandant"}),
    "accounti.export.datev_stammdaten.sachkontenlaenge": frozenset({"mandant"}),
    "accounti.export.datev_stammdaten.lade_datev_mandant": frozenset(
        {"datev", *_MANDANT_BUCHHALTUNG}
    ),
    "accounti.befehle.gesellschaft._wirtschaftsjahr": frozenset({"datev"}),
    # Verfahrensdokumentation: Kopf und Abschnitt 1 (mandant), Webhook (belegkanaele)
    "accounti.pruefung.verfahrensdoku._Doku.abschnitt": frozenset(
        {"mandant", "belegkanaele"}
    ),
    # Betrieb: immer aus der Datei
    "accounti.auth.einstellungen.lade_auth": frozenset({"auth"}),
    "accounti.api.einstellungen.lade_server": frozenset({"server"}),
    "accounti.betrieb.gesellschaften.lade_gesellschaften": frozenset(
        {"gesellschaften"}
    ),
}


def info(abschnitt: str) -> AbschnittInfo:
    return ABSCHNITTE.get(abschnitt, UNBEKANNT)
