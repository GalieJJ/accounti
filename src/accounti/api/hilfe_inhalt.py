"""Inhalt der Hilfe (Baustein 10c, Plan P1 Schritte 9 und 10) — als Daten, gerendert von
den Vorlagen der Hilfe und der Tastenhilfe der Arbeitsfläche.

``TASTEN_PRUEFEN`` ist die eine Quelle der Tasten der Prüfseite: Tastenhilfe, Hilfeseite
und der Test gegen ``statisch/pruefen.js`` lesen sie (P3 ändert die Bedeutungen hier).
"""

from __future__ import annotations

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
