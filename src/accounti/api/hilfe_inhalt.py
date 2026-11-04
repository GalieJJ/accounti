"""Inhalt der Hilfe (Spec 10c A8, AK47, AK57; Plan P1 Schritte 9 und 10) — als Daten,
gerendert von ``vorlagen/hilfe/`` und der Tastenhilfe der Arbeitsfläche.

- ``Hilfethema``: alle Bereiche der Navigation, dazu Anmeldung und Konto. Ein Thema ohne
  Eintrag in ``HILFE`` hat (noch) keine Seite: ``/hilfe/<thema>`` antwortet mit 404,
  ``fehlende_hilfe`` meldet den Bereich, sobald er eine Seite hat — jedes Paket, das
  einen Bereich einträgt, schreibt seine Hilfe mit.
- ``BEGRIFFE``: Anhang B der Spec (klare Sprache, Fachbegriff, Bedeutung).
- ``TASTEN_PRUEFEN``: die eine Quelle der Tasten der Prüfseite (Tastenhilfe, Hilfeseite,
  Test gegen ``statisch/pruefen.js``; P3 ändert die Bedeutungen hier).

Alle Texte laufen durch ``N_()`` (Katalog ``i18n/en.yaml``; ein „%“ steht als „%%“, weil
``_()`` in den Vorlagen formatiert); keine Daten einer
Gesellschaft, keine Links auf fremde Server.
"""

from __future__ import annotations

import enum
from collections.abc import Sequence
from dataclasses import dataclass

from accounti.api.registry import Bereich, Navigationspunkt
from accounti.i18n import N_

TASTEN_PRUEFEN: tuple[tuple[str, str], ...] = (
    ("j", N_("nächster Eintrag")),
    ("k", N_("voriger Eintrag")),
    ("f", N_("freigeben")),
    ("e", N_("korrigieren (Fokus auf Soll)")),
    ("r", N_("Regel daraus machen (an/aus)")),
    ("z", N_("zurückstellen (Fokus auf die Rückfrage)")),
    ("b", N_("Beleg in neuem Tab")),
    ("?", N_("diese Hilfe")),
)


class Hilfethema(str, enum.Enum):
    """Alle Bereiche (gleiche Werte wie ``registry.Bereich``) und zwei Seiten ohne
    Bereich."""

    UEBERSICHT = "uebersicht"
    PRUEFEN = "pruefen"
    BELEGE = "belege"
    BANK = "bank"
    RECHNUNGEN = "rechnungen"
    STEUERN = "steuern"
    AUSWERTUNGEN = "auswertungen"
    FREIGABEN = "freigaben"
    EINSTELLUNGEN = "einstellungen"
    ANMELDUNG = "anmeldung"
    KONTO = "konto"


@dataclass(frozen=True)
class Abschnitt:
    id: str  # Sprungziel (/hilfe/freigaben#zahlungslauf)
    titel: str
    absaetze: tuple[str, ...]


@dataclass(frozen=True)
class Hilfe:
    titel: str
    einleitung: str
    anleitung: tuple[str, ...]
    abschnitte: tuple[Abschnitt, ...] = ()
    tasten: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class Begriff:
    """Eine Zeile aus Anhang B: so heißt es in accounti, so in der Fachsprache."""

    klar: str
    fach: str
    erklaerung: str


HILFE: dict[Hilfethema, Hilfe] = {
    Hilfethema.UEBERSICHT: Hilfe(
        N_("Übersicht"),
        N_(
            "Die Übersicht zeigt, was in der aktiven Gesellschaft ansteht: offene "
            "Rechnungen, Buchungen und Belege zur Prüfung und Zahlungsläufe, die auf "
            "eine Freigabe warten."
        ),
        (
            N_(
                "Oben steht die aktive Gesellschaft mit Kennfarbe und Kürzel. "
                "Gewechselt wird über ihren Namen oder unter „Mehr“."
            ),
            N_(
                "Die Zahlen in der Navigation zählen offene Vorschläge (Prüfen) und "
                "Zahlungsläufe im Entwurf (Freigaben)."
            ),
            N_("Fällige offene Rechnungen stehen in der Liste darunter."),
        ),
    ),
    Hilfethema.PRUEFEN: Hilfe(
        N_("Prüfen"),
        N_(
            "Unter „Prüfen“ stehen Buchungsvorschläge, die accounti nicht sicher genug "
            "selbst buchen wollte."
        ),
        (
            N_("Einen Eintrag öffnen: links der Beleg, rechts der Vorschlag."),
            N_(
                "Passt der Vorschlag, freigeben. Sonst Konto und Steuer korrigieren — "
                "auf Wunsch lernt accounti daraus eine Regel."
            ),
            N_(
                "Ist etwas unklar, den Eintrag mit einer Rückfrage zurückstellen; er "
                "steht dann unter „Zurückgestellt“."
            ),
            N_(
                "Gelernte Regeln stehen unter „Gelernte Regeln“ und lassen sich "
                "abschalten."
            ),
        ),
        tasten=TASTEN_PRUEFEN,
    ),
    Hilfethema.FREIGABEN: Hilfe(
        N_("Freigaben"),
        N_(
            "Hier gibt eine berechtigte Person Zahlungsläufe und die "
            "Umsatzsteuer-Voranmeldung frei — immer mit einem frischen Code aus der "
            "Authenticator-App."
        ),
        (
            N_("Den Lauf prüfen: Empfänger, Beträge und Summe."),
            N_(
                "Den Code aus der Authenticator-App eingeben und freigeben. Hat sich "
                "der Lauf inzwischen geändert, zeigt accounti ihn neu an."
            ),
            N_("Ohne Freigaberecht ist die Seite nur zum Lesen da."),
        ),
        (
            Abschnitt(
                "zahlungslauf",
                N_("So entsteht ein Zahlungslauf"),
                (
                    N_(
                        "Zahlungsläufe legt die Buchhaltung in der Kommandozeile an: "
                        "accounti zahlung vorschlag zeigt die fälligen Rechnungen, "
                        "accounti zahlung anlegen macht daraus einen Lauf im Entwurf."
                    ),
                    N_("Danach steht der Lauf hier zur Freigabe."),
                ),
            ),
        ),
    ),
    Hilfethema.ANMELDUNG: Hilfe(
        N_("Anmeldung"),
        N_(
            "Zur Anmeldung gehören Benutzername, Passwort und ein Code aus der "
            "Authenticator-App."
        ),
        (
            N_(
                "Benutzername und Passwort eingeben — ein Passwortmanager darf beides "
                "einfügen."
            ),
            N_(
                "Den sechsstelligen Code aus der Authenticator-App eingeben. Ohne die "
                "App geht einer der Wiederherstellungscodes; jeder gilt nur einmal."
            ),
            N_(
                "Nach mehreren Fehlversuchen sperrt accounti die Anmeldung für kurze "
                "Zeit. Die Meldung sagt nie, was falsch war."
            ),
        ),
    ),
    Hilfethema.KONTO: Hilfe(
        N_("Mein Konto"),
        N_(
            "Unter „Mein Konto“ stellen Sie ein, wie accounti für Sie aussieht. Die "
            "Einstellungen gelten auf jedem Gerät."
        ),
        (
            N_("Sprache: automatisch folgt dem Browser, sonst Deutsch oder Englisch."),
            N_("Darstellung: automatisch folgt dem Gerät, sonst hell oder dunkel."),
            N_(
                "Die Fachansicht zeigt Konten, Soll und Haben und Steuerschlüssel; "
                "„Beträge verbergen“ blendet Beträge auf der Übersicht aus."
            ),
            N_(
                "Tastenkürzel gelten auf der Prüfseite; abschalten lassen sie sich "
                "hier oder in der Tastenhilfe."
            ),
        ),
    ),
}

BEGRIFFE: tuple[Begriff, ...] = (
    Begriff(
        N_("→ Betriebsbedarf (4980)"),
        N_("Soll 4980 / Haben 1200"),
        N_(
            "Das Konto, auf das ein Betrag gebucht wird; die Bankseite zeigt die "
            "Fachansicht."
        ),
    ),
    Begriff(
        N_("mit 19 %% Vorsteuer"),
        N_("Steuerschlüssel 9"),
        N_("Welche Steuer in einem Betrag steckt."),
    ),
    Begriff(
        N_("Sicherheit: mittel"),
        N_("Confidence 62 %%"),
        N_("Wie sicher accounti bei einem Vorschlag ist: niedrig, mittel oder hoch."),
    ),
    Begriff(
        N_("Vorschlag der KI"),
        N_("KI-Vorschlag (LLM) · Modell …"),
        N_("Ein Sprachmodell hat das Konto vorgeschlagen."),
    ),
    Begriff(
        N_("nach Ihrer Regel „X“"),
        N_("Regelwerk · Regel X"),
        N_("Eine gelernte oder eingetragene Regel hat das Konto bestimmt."),
    ),
    Begriff(
        N_("wie bisher bei diesem Lieferanten/Kunden"),
        N_("Kontakt"),
        N_("accounti bucht wie bei früheren Rechnungen desselben Kontakts."),
    ),
    Begriff(
        N_("Passt – freigeben"),
        N_("Freigeben"),
        N_("Der Vorschlag stimmt und wird gebucht."),
    ),
    Begriff(
        N_("Anderes Konto …"),
        N_("Korrigieren"),
        N_("Konto oder Steuer ändern, bevor gebucht wird."),
    ),
    Begriff(
        N_("Später klären …"),
        N_("Zurückstellen mit Rückfrage"),
        N_("Den Eintrag mit einer Frage beiseitelegen."),
    ),
    Begriff(
        N_("Künftig immer so?"),
        N_("Regel daraus machen · Muster (Text, nur ganze Wörter) · Suchen in"),
        N_("Aus einer Korrektur eine Regel für künftige Umsätze lernen."),
    ),
    Begriff(
        N_("Ausgaben / Einnahmen"),
        N_("Zahlungsrichtung"),
        N_("Ob Geld abgeht oder eingeht."),
    ),
    Begriff(
        N_("Empfänger / Absender"),
        N_("Gegenpartei"),
        N_("Wer Geld bekommt (Ausgabe) oder schickt (Einnahme)."),
    ),
    Begriff(
        N_("Verlauf"),
        N_("Buchung und Journal"),
        N_("Jede Änderung an einer Buchung, unveränderbar aufgezeichnet."),
    ),
    Begriff(
        N_("Code aus Ihrer Authenticator-App"),
        N_("Einmalcode"),
        N_("Der sechsstellige Code für die Anmeldung und für Freigaben."),
    ),
    Begriff(
        N_("Umsatzsteuer-Voranmeldung"),
        N_("USt-VA"),
        N_("Die regelmäßige Meldung der Umsatzsteuer an das Finanzamt."),
    ),
    Begriff(
        N_("offene Rechnungen"),
        N_("OPOS / offene Posten"),
        N_(
            "Rechnungen, die noch nicht bezahlt sind: Forderungen und "
            "Verbindlichkeiten."
        ),
    ),
    Begriff(
        N_("Buchung berichtigen (Storno)"),
        N_("Storno"),
        N_(
            "Eine freigegebene Buchung wird nicht geändert, sondern mit einer "
            "Gegenbuchung berichtigt."
        ),
    ),
)


def fehlende_hilfe(punkte: Sequence[Navigationspunkt]) -> list[Bereich]:
    """Bereiche mit einer Seite in der Registry, aber ohne Eintrag in ``HILFE``."""
    mit_seite = {p.bereich for p in punkte}
    return [b for b in Bereich if b in mit_seite and Hilfethema(b.value) not in HILFE]
