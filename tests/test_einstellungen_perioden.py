"""Periodenwerte „ab Zeitraum → Wert“ (Baustein 10c P4, Schritt 6; E3, A46, D14).

Ein Einzelwert gilt immer; eine Zuordnung ``{2026: monat, 2027: quartal}`` gilt je
Zeitraum mit dem größten Schlüssel ≤ Zeitraum, der früheste Eintrag auch davor. OSS
hat Quartalsschlüssel (``"2027-Q1"``), die Gewinnermittlung Wirtschaftsjahre (Jahr des
WJ-Endes). Jeder Verbraucher fragt mit seinem Zeitraum: Die Rohfelder heißen im Modell
``*_roh`` (Alias = Dateiname), ein alter Zugriff scheitert an mypy, und nur
``perioden.py`` und das Modul des Modells greifen auf ``*_roh`` zu.
"""

from __future__ import annotations

import ast
from datetime import date
from pathlib import Path

import pytest

from accounti.einstellungen.perioden import schluessel_fuer, setze_ab, wert_fuer
from accounti.konfiguration import KonfigurationError

SRC = Path(__file__).resolve().parents[1] / "src" / "accounti"


def test_einzelwert_gilt_immer():
    assert wert_fuer("quartal", 1990) == "quartal"
    assert wert_fuer(True, "2031-Q4") is True
    assert wert_fuer({2026: "monat"}, 2040) == "monat"


def test_ab_zeitraum_groesster_schluessel():
    wert = {2026: "monat", 2027: "quartal", 2030: "monat"}
    assert [wert_fuer(wert, j) for j in (2026, 2027, 2029, 2030, 2035)] == [
        "monat",
        "quartal",
        "quartal",
        "monat",
        "monat",
    ]


def test_fruehester_eintrag_gilt_auch_davor():
    assert wert_fuer({2027: "quartal", 2028: "monat"}, 2020) == "quartal"
    assert wert_fuer({"2027-Q2": True}, "2026-Q1") is True


def test_umwandlung_einzelwert():
    """D14: ``alt`` mit „ab Z: neu“ wird ``{Z−1: alt, Z: neu}`` — frühere Zeiträume
    behalten den alten Wert."""
    assert setze_ab("monat", 2027, "quartal") == {2026: "monat", 2027: "quartal"}
    assert setze_ab(False, "2027-Q1", True) == {"2026-Q4": False, "2027-Q1": True}
    assert setze_ab(False, "2027-Q3", True) == {"2027-Q2": False, "2027-Q3": True}
    vorher = {2026: "monat", 2028: "quartal"}
    assert setze_ab(vorher, 2027, "quartal") == {
        2026: "monat",
        2027: "quartal",
        2028: "quartal",
    }
    assert vorher == {2026: "monat", 2028: "quartal"}  # unverändert
    # früher als jeder Eintrag: die Zeiträume davor behalten den alten Wert
    assert setze_ab({2028: "quartal"}, 2026, "monat") == {
        2025: "quartal",
        2026: "monat",
        2028: "quartal",
    }


def test_quartalsschluessel_oss():
    assert schluessel_fuer("quartal", date(2027, 2, 14)) == "2027-Q1"
    assert schluessel_fuer("quartal", date(2027, 12, 31)) == "2027-Q4"
    oss = {"2026-Q1": False, "2027-Q1": True}
    assert wert_fuer(oss, schluessel_fuer("quartal", date(2026, 12, 31))) is False
    assert wert_fuer(oss, schluessel_fuer("quartal", date(2027, 1, 1))) is True
    assert schluessel_fuer("jahr", date(2027, 5, 1)) == 2027
    assert schluessel_fuer("jahr", 2027) == 2027


def test_wirtschaftsjahr_schluessel_abweichendes_wj():
    """WJ nach Paket F: benannt nach dem Kalenderjahr seines Endes."""
    juli = date(2000, 7, 1)
    assert schluessel_fuer("wirtschaftsjahr", date(2026, 6, 30), beginn=juli) == 2026
    assert schluessel_fuer("wirtschaftsjahr", date(2026, 7, 1), beginn=juli) == 2027
    assert schluessel_fuer("wirtschaftsjahr", date(2026, 7, 1)) == 2026
    gewinn = {2026: "euer", 2027: "bilanz"}
    tag = date(2026, 8, 15)
    assert wert_fuer(gewinn, schluessel_fuer("wirtschaftsjahr", tag)) == "euer"
    wj = schluessel_fuer("wirtschaftsjahr", tag, beginn=juli)
    assert wert_fuer(gewinn, wj) == "bilanz"


@pytest.mark.parametrize(
    ("abschnitt", "inhalt", "feld"),
    [
        ("elster", "voranmeldungszeitraum: {abc: quartal}", "voranmeldungszeitraum"),
        ("elster", "voranmeldungszeitraum: {2027: woche}", "voranmeldungszeitraum"),
        ("elster", "voranmeldungszeitraum: {}", "voranmeldungszeitraum"),
        (
            "elster",
            "dauerfristverlaengerung: {2027-Q1: true}",
            "dauerfristverlaengerung",
        ),
        ("mandant", "oss: {2027: true}", "oss"),
        ("mandant", "oss: {2027-Q5: true}", "oss"),
        (
            "abschluss",
            "gewinnermittlung: {2027: bilanz, 2028: gewinn}",
            "gewinnermittlung",
        ),
    ],
)
def test_ungueltiger_schluessel_nennt_pfad(tmp_path, abschnitt, inhalt, feld):
    from accounti.abschluss.konfiguration import lade_abschluss
    from accounti.elster.konfiguration import lade_elster
    from accounti.konfiguration import lade_firma

    pfad = tmp_path / "accounti.yaml"
    mandant = (
        "mandant:\n  name: X\n  ust_id: DE1\n  email: a@b.example\n"
        "  anschrift: {strasse: a, plz: '1', ort: b}\n"
        "  kontakt: {name: a, telefon: '1', email: a@b.example}\n"
        "  bank: {iban: DE89370400440532013000}\n"
    )
    if abschnitt == "mandant":
        text = mandant + f"  {inhalt}\n"
    else:
        text = f"{abschnitt}:\n  {inhalt}\n"
    pfad.write_text(text, encoding="utf-8")
    lader = {"elster": lade_elster, "mandant": lade_firma, "abschluss": lade_abschluss}
    with pytest.raises(KonfigurationError) as fehler:
        lader[abschnitt](pfad)
    text = str(fehler.value)
    # lade_abschluss nennt Abschnitt und Feld getrennt (Meldung wie vor 10c)
    assert f"{abschnitt}.{feld}" in text or (
        f"Abschnitt '{abschnitt}'" in text and feld in text
    ), text


def test_rohfelder_heissen_anders_als_in_der_datei():
    """M6: Das Rohfeld trägt den Dateinamen nur als Alias —
    ``model_dump(by_alias=True)`` schreibt den Dateinamen, einen Zugriff über den
    Dateinamen gibt es nicht."""
    from accounti.abschluss.konfiguration import AbschlussEinstellungen
    from accounti.elster.konfiguration import ElsterEinstellungen
    from accounti.konfiguration import Firma

    elster = ElsterEinstellungen(voranmeldungszeitraum={2026: "monat", 2027: "quartal"})
    assert elster.voranmeldungszeitraum_fuer(2026) == "monat"
    assert elster.voranmeldungszeitraum_fuer(2027) == "quartal"
    assert elster.dauerfrist_fuer(2027) is False
    dump = elster.model_dump(mode="json", by_alias=True)
    assert dump["voranmeldungszeitraum"] == {"2026": "monat", "2027": "quartal"}
    assert not hasattr(elster, "voranmeldungszeitraum")
    assert "oss" in Firma.model_fields["oss_roh"].alias  # type: ignore[operator]
    gewinn = AbschlussEinstellungen(
        ergebnis_konto="0880",
        arap_konto="0980",
        prap_konto="0990",
        gewinnermittlung={2026: "euer", 2027: "bilanz"},
    )
    assert gewinn.gewinnermittlung_fuer(2027) == "bilanz"
    # aus der Datenbank kommen die Schlüssel als Text (JSON)
    aus_json = ElsterEinstellungen.model_validate(
        {"voranmeldungszeitraum": {"2026": "monat", "2027": "quartal"}}
    )
    assert aus_json.voranmeldungszeitraum_fuer(2027) == "quartal"


def _rohzugriffe() -> list[str]:
    funde = []
    for datei in SRC.rglob("*.py"):
        relativ = datei.relative_to(SRC).as_posix()
        baum = ast.parse(datei.read_text(encoding="utf-8"))
        definiert = {
            k.target.id
            for k in ast.walk(baum)
            if isinstance(k, ast.AnnAssign) and isinstance(k.target, ast.Name)
        }
        for k in ast.walk(baum):
            if (
                isinstance(k, ast.Attribute)
                and k.attr.endswith("_roh")
                and relativ != "einstellungen/perioden.py"
                and k.attr not in definiert
            ):
                funde.append(f"{relativ}:{k.lineno} {k.attr}")
    return funde


def test_kein_zugriff_auf_rohfelder():
    """M6: ``*_roh`` nur in ``perioden.py`` und im Modul, das das Feld definiert."""
    assert _rohzugriffe() == []


def test_model_copy_nimmt_auch_den_dateinamen():
    """``model_copy(update={"oss": True})`` (Dateiname) setzt das Rohfeld — sonst
    bliebe es still beim alten Wert."""
    from accounti.elster.konfiguration import ElsterEinstellungen
    from tests.test_erechnung_aufbau import FIRMA

    assert FIRMA.model_copy(update={"oss": True}).oss_am(date(2026, 3, 1)) is True
    assert FIRMA.model_copy(update={"oss_roh": True}).oss_am(date(2026, 3, 1)) is True
    elster = ElsterEinstellungen().model_copy(update={"dauerfristverlaengerung": True})
    assert elster.dauerfrist_fuer(2026) is True


@pytest.mark.parametrize(
    ("art", "roh", "grund"),
    [
        # Datenbank (JSON) und gequotete YAML-Schlüssel sind Text: dieselbe Prüfung
        ("jahr", {"2026": "monat", "3027": "quartal"}, "3027"),
        ("jahr", {"2026": "monat", "0207": "quartal"}, "0207"),
        ("jahr", {"1899": "monat"}, "1899"),
        ("wirtschaftsjahr", {"2026": "euer", "3000": "bilanz"}, "3000"),
        ("quartal", {"2026-Q1": False, "0207-Q1": True}, "0207-Q1"),
        ("quartal", {"3027-Q1": True}, "3027-Q1"),
        ("jahr", {3027: "quartal"}, "3027"),
    ],
)
def test_schluessel_als_text_im_bereich(art, roh, grund):
    """Prüfung steuer-4: Die Bereichsprüfung 1900–2999 gilt auch für Text-Schlüssel
    und das Jahr in ``JJJJ-Qn`` — „0207“ schaltete sonst still alle Jahre vor 2026
    um, „3027“ wirkte nie."""
    from accounti.einstellungen.perioden import pruefe

    typ = {"jahr": str, "wirtschaftsjahr": str, "quartal": bool}[art]
    with pytest.raises(ValueError, match=f"Schlüssel '?{grund}'?") as fehler:
        pruefe(art, typ)(roh)
    assert "1900" in str(fehler.value) and "2999" in str(fehler.value)


@pytest.mark.parametrize(
    ("art", "roh"),
    [
        ("jahr", {2026: "monat", "2026": "quartal"}),
        ("jahr", {"2026": "monat", " 2026": "quartal"}),
        ("quartal", {"2026-Q1": False, " 2026-Q1": True}),
        ("wirtschaftsjahr", {2027: "euer", "2027": "bilanz"}),
    ],
)
def test_doppelter_schluessel_nach_normalisierung_ist_ein_fehler(art, roh):
    """Prüfung steuer-4: 2026 und "2026" fielen still zu einem Eintrag zusammen (der
    letzte gewann)."""
    from accounti.einstellungen.perioden import pruefe

    typ = {"jahr": str, "wirtschaftsjahr": str, "quartal": bool}[art]
    with pytest.raises(ValueError, match="doppelt"):
        pruefe(art, typ)(roh)


def test_gueltige_text_schluessel_wie_bisher():
    from accounti.einstellungen.perioden import pruefe

    assert pruefe("jahr", str)({"2027": "quartal", 2026: "monat"}) == {
        2026: "monat",
        2027: "quartal",
    }
    assert pruefe("quartal", bool)({" 2027-Q1": True, "1900-Q4": False}) == {
        "1900-Q4": False,
        "2027-Q1": True,
    }
    assert pruefe("jahr", str)({"2999": "monat"}) == {2999: "monat"}
