"""Tests für das Steuer-Modul: Umsatzsteuer, OSS, EU-Steuersätze."""

from decimal import Decimal

import pytest

from accounti.steuer.eu_steuersaetze import (
    EU_STEUERSAETZE,
    ist_eu_land,
    ist_oss_land,
    steuersatz_fuer_land,
)
from accounti.steuer.umsatzsteuer import (
    Geschaeftsvorfall,
    UStBerechner,
)
from accounti.steuer.oss import OSSEngine, OSS_SCHWELLE_EUR


# ===================================================================
# EU-Steuersätze
# ===================================================================


class TestEUSteuersaetze:
    def test_alle_27_eu_laender_vorhanden(self) -> None:
        eu_laender = [s for s in EU_STEUERSAETZE.values() if s.eu_mitglied]
        assert len(eu_laender) == 27

    def test_deutschland_19_prozent(self) -> None:
        de = EU_STEUERSAETZE["DE"]
        assert de.normal == Decimal("19")
        assert de.ermaessigt == Decimal("7")
        assert de.eu_mitglied is True
        assert de.oss_faehig is True

    def test_frankreich_20_prozent(self) -> None:
        fr = EU_STEUERSAETZE["FR"]
        assert fr.normal == Decimal("20")
        assert fr.ermaessigt == Decimal("5.5")

    def test_ungarn_hoechster_satz(self) -> None:
        hu = EU_STEUERSAETZE["HU"]
        assert hu.normal == Decimal("27")

    def test_uk_kein_eu_mitglied(self) -> None:
        gb = EU_STEUERSAETZE["GB"]
        assert gb.eu_mitglied is False
        assert gb.oss_faehig is False

    def test_ist_eu_land(self) -> None:
        assert ist_eu_land("DE") is True
        assert ist_eu_land("FR") is True
        assert ist_eu_land("GB") is False
        assert ist_eu_land("US") is False

    def test_ist_oss_land(self) -> None:
        assert ist_oss_land("FR") is True
        assert ist_oss_land("IT") is True
        assert ist_oss_land("GB") is False

    def test_steuersatz_fuer_land_unbekannt(self) -> None:
        with pytest.raises(KeyError, match="Unbekannter Ländercode"):
            steuersatz_fuer_land("XX")

    def test_normal_faktor(self) -> None:
        de = EU_STEUERSAETZE["DE"]
        assert de.normal_faktor == Decimal("0.19")

    def test_alle_laender_haben_normalsatz(self) -> None:
        for code, info in EU_STEUERSAETZE.items():
            assert info.normal > 0, f"{code} hat keinen Normalsatz"

    def test_alle_laender_haben_waehrung(self) -> None:
        for code, info in EU_STEUERSAETZE.items():
            assert len(info.waehrung) == 3, f"{code} hat ungültige Währung"


# ===================================================================
# Umsatzsteuer-Berechner
# ===================================================================


class TestUStBerechner:
    """Tests für die Kernfunktionen der USt-Berechnung."""

    def setup_method(self) -> None:
        self.berechner = UStBerechner(firmen_land="DE")

    # --- Geschäftsvorfall-Bestimmung ---

    def test_inland_verkauf(self) -> None:
        vorfall = self.berechner.bestimme_vorfall("DE")
        assert vorfall == Geschaeftsvorfall.INLAND

    def test_eu_b2c_oss(self) -> None:
        vorfall = self.berechner.bestimme_vorfall("FR", ist_b2b=False)
        assert vorfall == Geschaeftsvorfall.EU_B2C_OSS

    def test_eu_b2b_reverse_charge(self) -> None:
        vorfall = self.berechner.bestimme_vorfall(
            "FR", ist_b2b=True, kaeufer_hat_ust_id=True
        )
        assert vorfall == Geschaeftsvorfall.EU_INNERGEMEINSCHAFTLICH

    def test_eu_b2b_ohne_ust_id_ist_b2c(self) -> None:
        """B2B ohne USt-ID wird wie B2C behandelt."""
        vorfall = self.berechner.bestimme_vorfall(
            "FR", ist_b2b=True, kaeufer_hat_ust_id=False
        )
        assert vorfall == Geschaeftsvorfall.EU_B2C_OSS

    def test_drittland(self) -> None:
        vorfall = self.berechner.bestimme_vorfall("US")
        assert vorfall == Geschaeftsvorfall.DRITTLAND_AUSFUHR

    def test_uk_ist_drittland(self) -> None:
        vorfall = self.berechner.bestimme_vorfall("GB")
        assert vorfall == Geschaeftsvorfall.DRITTLAND_AUSFUHR

    def test_schweiz_ist_drittland(self) -> None:
        vorfall = self.berechner.bestimme_vorfall("CH")
        assert vorfall == Geschaeftsvorfall.DRITTLAND_AUSFUHR

    def test_unter_schwelle_kein_oss(self) -> None:
        berechner = UStBerechner(
            firmen_land="DE",
            oss_registriert=True,
            oss_schwelle_ueberschritten=False,
        )
        vorfall = berechner.bestimme_vorfall("FR", ist_b2b=False)
        assert vorfall == Geschaeftsvorfall.INLAND

    # --- USt-Berechnung ---

    def test_inland_19_prozent(self) -> None:
        pos = self.berechner.berechne_ust(Decimal("100.00"), "DE")
        assert pos.steuersatz == Decimal("19")
        assert pos.steuerbetrag == Decimal("19.00")
        assert pos.brutto == Decimal("119.00")
        assert pos.steuer_konto == "1776"

    def test_inland_7_prozent(self) -> None:
        pos = self.berechner.berechne_ust(Decimal("100.00"), "DE", ermaessigt=True)
        assert pos.steuersatz == Decimal("7")
        assert pos.steuerbetrag == Decimal("7.00")
        assert pos.brutto == Decimal("107.00")

    def test_oss_frankreich(self) -> None:
        pos = self.berechner.berechne_ust(Decimal("100.00"), "FR")
        assert pos.steuersatz == Decimal("20")
        assert pos.steuerbetrag == Decimal("20.00")
        assert pos.geschaeftsvorfall == Geschaeftsvorfall.EU_B2C_OSS

    def test_oss_italien(self) -> None:
        pos = self.berechner.berechne_ust(Decimal("100.00"), "IT")
        assert pos.steuersatz == Decimal("22")
        assert pos.steuerbetrag == Decimal("22.00")

    def test_oss_schweden(self) -> None:
        pos = self.berechner.berechne_ust(Decimal("100.00"), "SE")
        assert pos.steuersatz == Decimal("25")
        assert pos.steuerbetrag == Decimal("25.00")

    def test_oss_polen(self) -> None:
        pos = self.berechner.berechne_ust(Decimal("100.00"), "PL")
        assert pos.steuersatz == Decimal("23")

    def test_ig_lieferung_steuerfrei(self) -> None:
        pos = self.berechner.berechne_ust(
            Decimal("100.00"), "FR", ist_b2b=True, kaeufer_hat_ust_id=True
        )
        assert pos.steuersatz == Decimal("0")
        assert pos.steuerbetrag == Decimal("0.00")
        assert pos.brutto == Decimal("100.00")

    def test_drittland_steuerfrei(self) -> None:
        pos = self.berechner.berechne_ust(Decimal("100.00"), "US")
        assert pos.steuersatz == Decimal("0")
        assert pos.brutto == Decimal("100.00")

    def test_rundung_korrekt(self) -> None:
        """19% auf 33.33€ = 6.3327 → 6.33€."""
        pos = self.berechner.berechne_ust(Decimal("33.33"), "DE")
        assert pos.steuerbetrag == Decimal("6.33")
        assert pos.brutto == Decimal("39.66")

    # --- Vorsteuer ---

    def test_vorsteuer_berechnung(self) -> None:
        pos = self.berechner.berechne_vst(Decimal("119.00"), Decimal("19"))
        assert pos.netto == Decimal("100.00")
        assert pos.steuerbetrag == Decimal("19.00")
        assert pos.steuer_konto == "1576"
        assert pos.geschaeftsvorfall == Geschaeftsvorfall.VORSTEUER

    def test_vorsteuer_7_prozent(self) -> None:
        pos = self.berechner.berechne_vst(Decimal("107.00"), Decimal("7"))
        assert pos.netto == Decimal("100.00")
        assert pos.steuerbetrag == Decimal("7.00")
        assert pos.steuer_konto == "1571"

    # --- Netto/Brutto-Umrechnung ---

    def test_netto_zu_brutto(self) -> None:
        brutto = self.berechner.netto_zu_brutto(Decimal("100.00"), Decimal("19"))
        assert brutto == Decimal("119.00")

    def test_brutto_zu_netto(self) -> None:
        netto = self.berechner.brutto_zu_netto(Decimal("119.00"), Decimal("19"))
        assert netto == Decimal("100.00")

    def test_brutto_netto_roundtrip(self) -> None:
        """Netto → Brutto → Netto sollte den Ausgangswert ergeben."""
        netto_original = Decimal("83.47")
        brutto = self.berechner.netto_zu_brutto(netto_original, Decimal("19"))
        netto_zurueck = self.berechner.brutto_zu_netto(brutto, Decimal("19"))
        assert netto_zurueck == netto_original


# ===================================================================
# Alle Marketplace-Länder testen (dein Use Case)
# ===================================================================


class TestMultiMarketplace:
    """Tests für alle Marketplace-Länder: DE/FR/IT/ES/NL/UK/SE/PL."""

    def setup_method(self) -> None:
        self.berechner = UStBerechner(firmen_land="DE")

    @pytest.mark.parametrize(
        "land,erwarteter_satz",
        [
            ("DE", Decimal("19")),
            ("FR", Decimal("20")),
            ("IT", Decimal("22")),
            ("ES", Decimal("21")),
            ("NL", Decimal("21")),
            ("SE", Decimal("25")),
            ("PL", Decimal("23")),
        ],
    )
    def test_marketplace_steuersaetze(
        self, land: str, erwarteter_satz: Decimal
    ) -> None:
        pos = self.berechner.berechne_ust(Decimal("100.00"), land)
        assert pos.steuersatz == erwarteter_satz

    def test_uk_marketplace_steuerfrei(self) -> None:
        """UK ist seit Brexit Drittland → steuerfrei."""
        pos = self.berechner.berechne_ust(Decimal("100.00"), "GB")
        assert pos.steuersatz == Decimal("0")
        assert pos.geschaeftsvorfall == Geschaeftsvorfall.DRITTLAND_AUSFUHR


# ===================================================================
# OSS-Engine
# ===================================================================


class TestOSSEngine:
    def test_schwelle_wert(self) -> None:
        assert OSS_SCHWELLE_EUR == Decimal("10000.00")

    def test_quartal_berechnung(self) -> None:
        from datetime import date

        engine = OSSEngine()
        assert engine._quartal_fuer_datum(date(2026, 1, 15)) == (2026, 1)
        assert engine._quartal_fuer_datum(date(2026, 4, 1)) == (2026, 2)
        assert engine._quartal_fuer_datum(date(2026, 7, 31)) == (2026, 3)
        assert engine._quartal_fuer_datum(date(2026, 12, 31)) == (2026, 4)

    def test_leere_meldung(self) -> None:
        engine = OSSEngine()
        meldung = engine.erstelle_meldung([], 2026, 2)
        assert meldung.quartal == "2026-Q2"
        assert meldung.anzahl_transaktionen == 0
        assert meldung.steuer_gesamt == Decimal("0.00")
