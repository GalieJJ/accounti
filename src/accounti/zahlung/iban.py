"""IBAN-Hilfen für den Zahlungsverkehr: Schreibweise, Prüfziffer, SEPA-Raum."""

from __future__ import annotations

import re

from accounti.belege.extraktion import iban_gueltig

_FORM = re.compile(r"[A-Z]{2}[0-9]{2}[A-Z0-9]{11,30}")

# IBAN-Länderkennzeichen im geografischen Geltungsbereich der SEPA-Verfahren:
# EPC409-09 „EPC List of SEPA Scheme Countries“ v8.0 vom 24.12.2025 — 27 EU-Staaten,
# 3 EWR-Staaten, 11 Nicht-EWR-Länder, dazu Gibraltar (GI). Guernsey, Jersey und Isle
# of Man führen GB-IBANs, die französischen Überseegebiete FR-IBANs.
EU = frozenset(
    {
        *("AT", "BE", "BG", "CY", "CZ", "DE", "DK", "EE", "ES", "FI", "FR", "GR"),
        *("HR", "HU", "IE", "IT", "LT", "LU", "LV", "MT", "NL", "PL", "PT", "RO"),
        *("SE", "SI", "SK"),
    }
)
EWR = EU | {"IS", "LI", "NO"}
NICHT_EWR = frozenset(
    {"AD", "AL", "CH", "GB", "GI", "MC", "MD", "ME", "MK", "RS", "SM", "VA"}
)
SEPA_LAENDER = EWR | NICHT_EWR


def normalisiere(iban: str | None) -> str:
    """Ohne Leerzeichen, in Großbuchstaben; ``None`` wird zu ``""``."""
    return re.sub(r"\s", "", iban or "").upper()


def gueltig(iban: str | None) -> bool:
    """Form und Prüfziffer (ISO 13616, Modulo 97)."""
    wert = normalisiere(iban)
    return bool(_FORM.fullmatch(wert)) and iban_gueltig(wert)


def im_sepa_raum(iban: str | None) -> bool:
    return normalisiere(iban)[:2] in SEPA_LAENDER


def lesbar(iban: str | None) -> str:
    """``DE89370400440532013000`` → ``DE89 3704 0044 0532 0130 00``."""
    wert = normalisiere(iban)
    return " ".join(wert[i : i + 4] for i in range(0, len(wert), 4))
