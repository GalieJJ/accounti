"""USt-Voranmeldung — Umsatzsteuer-Voranmeldung für ELSTER.

Berechnet die Kennziffern für die monatliche/quartalsweise
Umsatzsteuer-Voranmeldung aus den Buchungssätzen.

Hinweis: OSS-Umsätze werden NICHT in der USt-VA gemeldet,
sondern separat über das BZSt-Portal. Sie tauchen hier
nur informativ auf.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, ROUND_HALF_UP


@dataclass
class UStKennziffer:
    """Eine Kennziffer der Umsatzsteuer-Voranmeldung."""

    kz: int                    # ELSTER-Kennziffer (z.B. 81, 86, 66)
    bezeichnung: str
    bemessungsgrundlage: Decimal = Decimal("0.00")
    steuerbetrag: Decimal = Decimal("0.00")

    @property
    def hat_werte(self) -> bool:
        return self.bemessungsgrundlage != 0 or self.steuerbetrag != 0


@dataclass
class UStVoranmeldung:
    """Vollständige Umsatzsteuer-Voranmeldung für einen Meldezeitraum."""

    zeitraum: str              # z.B. "2026-04" oder "2026-Q1"
    firmen_name: str = ""
    steuernummer: str = ""
    ust_id: str = ""           # z.B. "DE123456789"

    # --- Abschnitt: Steuerpflichtige Umsätze ---
    # Kz 81: Umsätze zum Steuersatz von 19%
    kz_81: UStKennziffer = field(
        default_factory=lambda: UStKennziffer(81, "Umsätze 19%")
    )
    # Kz 86: Umsätze zum Steuersatz von 7%
    kz_86: UStKennziffer = field(
        default_factory=lambda: UStKennziffer(86, "Umsätze 7%")
    )
    # Kz 35: Umsätze anderer Steuersätze
    kz_35: UStKennziffer = field(
        default_factory=lambda: UStKennziffer(35, "Umsätze andere Steuersätze")
    )

    # --- Abschnitt: Steuerfreie Umsätze ---
    # Kz 41: Innergemeinschaftliche Lieferungen (§ 4 Nr. 1b)
    kz_41: UStKennziffer = field(
        default_factory=lambda: UStKennziffer(41, "Innergemeinschaftliche Lieferungen")
    )
    # Kz 43: Weitere steuerfreie Umsätze mit Vorsteuerabzug (Ausfuhr)
    kz_43: UStKennziffer = field(
        default_factory=lambda: UStKennziffer(43, "Ausfuhrlieferungen")
    )

    # --- Abschnitt: Innergemeinschaftliche Erwerbe ---
    # Kz 89: ig. Erwerbe zum Steuersatz von 19%
    kz_89: UStKennziffer = field(
        default_factory=lambda: UStKennziffer(89, "Innergemeinschaftliche Erwerbe")
    )

    # --- Abschnitt: Ergänzende Angaben ---
    # Kz 46: § 13b UStG (Reverse Charge, Leistungsempfänger)
    kz_46: UStKennziffer = field(
        default_factory=lambda: UStKennziffer(
            46, "Leistungen Reverse Charge § 13b"
        )
    )

    # --- Abschnitt: Abziehbare Vorsteuerbeträge ---
    # Kz 66: Vorsteuerbeträge aus Rechnungen
    kz_66: UStKennziffer = field(
        default_factory=lambda: UStKennziffer(66, "Vorsteuer aus Rechnungen")
    )
    # Kz 61: Vorsteuer aus ig. Erwerben
    kz_61: UStKennziffer = field(
        default_factory=lambda: UStKennziffer(61, "Vorsteuer ig. Erwerbe")
    )
    # Kz 67: Vorsteuer § 13b
    kz_67: UStKennziffer = field(
        default_factory=lambda: UStKennziffer(67, "Vorsteuer § 13b")
    )

    # --- Informativ (nicht Teil der USt-VA) ---
    oss_hinweis: Decimal = Decimal("0.00")  # OSS-Umsätze zur Info

    @property
    def umsatzsteuer_gesamt(self) -> Decimal:
        """Summe aller Umsatzsteuer (Kz 81 + 86 + 35 + 89 + 46)."""
        return (
            self.kz_81.steuerbetrag
            + self.kz_86.steuerbetrag
            + self.kz_35.steuerbetrag
            + self.kz_89.steuerbetrag
            + self.kz_46.steuerbetrag
        )

    @property
    def vorsteuer_gesamt(self) -> Decimal:
        """Summe aller Vorsteuer (Kz 66 + 61 + 67)."""
        return (
            self.kz_66.steuerbetrag
            + self.kz_61.steuerbetrag
            + self.kz_67.steuerbetrag
        )

    @property
    def zahllast(self) -> Decimal:
        """Verbleibende Zahllast (USt - VSt). Negativ = Erstattung."""
        return self.umsatzsteuer_gesamt - self.vorsteuer_gesamt

    def alle_kennziffern(self) -> list[UStKennziffer]:
        """Gibt alle Kennziffern als Liste zurück."""
        return [
            self.kz_81, self.kz_86, self.kz_35,
            self.kz_41, self.kz_43,
            self.kz_89,
            self.kz_46,
            self.kz_66, self.kz_61, self.kz_67,
        ]

    def zusammenfassung(self) -> str:
        """Textuelle Zusammenfassung der Voranmeldung."""
        zeilen = [
            f"USt-Voranmeldung {self.zeitraum}",
            "=" * 50,
            "",
            "Steuerpflichtige Umsätze:",
        ]
        for kz in [self.kz_81, self.kz_86, self.kz_35]:
            if kz.hat_werte:
                zeilen.append(
                    f"  Kz {kz.kz}: {kz.bezeichnung:<40} "
                    f"BMG: {kz.bemessungsgrundlage:>12.2f} € "
                    f"USt: {kz.steuerbetrag:>10.2f} €"
                )

        zeilen.append("\nSteuerfreie Umsätze:")
        for kz in [self.kz_41, self.kz_43]:
            if kz.hat_werte:
                zeilen.append(
                    f"  Kz {kz.kz}: {kz.bezeichnung:<40} "
                    f"BMG: {kz.bemessungsgrundlage:>12.2f} €"
                )

        zeilen.append("\nVorsteuer:")
        for kz in [self.kz_66, self.kz_61, self.kz_67]:
            if kz.hat_werte:
                zeilen.append(
                    f"  Kz {kz.kz}: {kz.bezeichnung:<40} "
                    f"VSt: {kz.steuerbetrag:>10.2f} €"
                )

        zeilen.extend([
            "",
            "-" * 50,
            f"  Umsatzsteuer gesamt:  {self.umsatzsteuer_gesamt:>10.2f} €",
            f"  Vorsteuer gesamt:     {self.vorsteuer_gesamt:>10.2f} €",
            f"  {'Zahllast' if self.zahllast >= 0 else 'Erstattung'}:"
            f"           {abs(self.zahllast):>10.2f} €",
        ])

        if self.oss_hinweis > 0:
            zeilen.extend([
                "",
                f"  [Info] OSS-Umsätze (separat zu melden): {self.oss_hinweis:>10.2f} €",
            ])

        return "\n".join(zeilen)
