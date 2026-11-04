from datetime import date

import pytest

from accounti.konfiguration import (
    KonfigurationError,
    lade_firma,
    lade_ustid_pruefung,
)
from accounti.kontakte.ustid import EVATR_URL

VOLL = """
mandant:
  name: "Galerie Muster GmbH"
  kuerzel: GM
  kontenrahmen: SKR03
  anschrift:
    strasse: "Beispielweg 3"
    plz: "24103"
    ort: Kiel
    land: DE
  ust_id: DE999999999
  steuernummer: "19/123/45678"
  email: rechnung@galerie-muster.example
  kontakt:
    name: Jan Muster
    telefon: "0431 123456"
    email: buchhaltung@galerie-muster.example
  bank:
    iban: "DE89 3704 0044 0532 0130 00"
    bic: COBADEFFXXX
  rechnung:
    nummernformat: "RE-{jahr}-{nummer:05d}"
    zahlungsziel_tage: 30
"""


def test_lade_firma(tmp_path):
    pfad = tmp_path / "accounti.yaml"
    pfad.write_text(VOLL, encoding="utf-8")
    f = lade_firma(pfad)
    assert f.name == "Galerie Muster GmbH"
    assert f.kuerzel == "GM"
    assert (f.anschrift.ort, f.anschrift.land) == ("Kiel", "DE")
    assert f.iban == "DE89370400440532013000"
    assert f.nummer(2026, 7) == "RE-2026-00007"
    assert f.zahlungsziel_tage == 30
    assert f.kontakt.telefon == "0431 123456"


def test_standardwerte(tmp_path):
    pfad = tmp_path / "accounti.yaml"
    pfad.write_text(
        VOLL.replace("  kuerzel: GM\n", "").split("  rechnung:")[0], encoding="utf-8"
    )
    f = lade_firma(pfad)
    assert f.kuerzel == "Galerie Muster GmbH"
    assert f.nummer(2026, 42) == "2026-0042"
    assert f.zahlungsziel_tage == 14


def test_fehlende_datei(tmp_path):
    with pytest.raises(KonfigurationError, match="accounti.example.yaml"):
        lade_firma(tmp_path / "gibtsnicht.yaml")


def test_fehlende_pflichtangaben_werden_benannt(tmp_path):
    pfad = tmp_path / "accounti.yaml"
    pfad.write_text('mandant:\n  name: "X GmbH"\n', encoding="utf-8")
    with pytest.raises(KonfigurationError) as info:
        lade_firma(pfad)
    meldung = str(info.value)
    for feld in ("anschrift", "email", "kontakt", "bank"):
        assert feld in meldung


def test_ust_id_oder_steuernummer_pflicht(tmp_path):
    pfad = tmp_path / "accounti.yaml"
    text = VOLL.replace("  ust_id: DE999999999\n", "").replace(
        '  steuernummer: "19/123/45678"\n', ""
    )
    pfad.write_text(text, encoding="utf-8")
    with pytest.raises(KonfigurationError, match="USt-IdNr. oder Steuernummer"):
        lade_firma(pfad)


def test_ungueltige_iban(tmp_path):
    pfad = tmp_path / "accounti.yaml"
    pfad.write_text(VOLL.replace("DE89 3704", "DE00 3704"), encoding="utf-8")
    with pytest.raises(KonfigurationError, match="IBAN"):
        lade_firma(pfad)


def test_ustid_pruefung_standard(tmp_path, monkeypatch):
    monkeypatch.delenv("ACCOUNTI_EVATR_URL", raising=False)
    e = lade_ustid_pruefung(tmp_path / "fehlt.yaml")
    assert (e.url, e.timeout_sekunden, e.max_alter_tage) == (EVATR_URL, 60, 30)


def test_ustid_pruefung_aus_datei_und_umgebung(tmp_path, monkeypatch):
    konfig = tmp_path / "accounti.yaml"
    konfig.write_text(
        "ustid_pruefung:\n  max_alter_tage: 0\n  timeout_sekunden: 20\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("ACCOUNTI_EVATR_URL", "http://127.0.0.1:9/app/v1/abfrage")
    e = lade_ustid_pruefung(konfig)
    assert (e.url, e.timeout_sekunden, e.max_alter_tage) == (
        "http://127.0.0.1:9/app/v1/abfrage",
        20,
        0,
    )


def test_ustid_pruefung_ungueltig(tmp_path):
    konfig = tmp_path / "accounti.yaml"
    konfig.write_text("ustid_pruefung:\n  max_alter_tage: -1\n", encoding="utf-8")
    with pytest.raises(KonfigurationError, match="ustid_pruefung"):
        lade_ustid_pruefung(konfig)


# --- Kontenrahmen aus einer Quelle (Gesamttest Betrieb B4 = Steuer B3 = Abschluss B6)


@pytest.mark.parametrize(
    ("text", "erwartet"),
    [
        ("mandant:\n  kontenrahmen: SKR04\n", "SKR04"),  # so stand es in der Vorlage
        ("buchhaltung:\n  kontenrahmen: skr04\n", "SKR04"),
        (
            "mandant:\n  kontenrahmen: SKR04\nbuchhaltung:\n  kontenrahmen: SKR04\n",
            "SKR04",
        ),
        ("buchhaltung:\n  bank_konto: '1200'\n", "SKR03"),
    ],
)
def test_kontenrahmen_aus_buchhaltung_oder_mandant(tmp_path, text, erwartet):
    from datetime import date

    from accounti.export.datev_stammdaten import lade_datev_mandant
    from accounti.konfiguration import lade_buchhaltung

    pfad = tmp_path / "accounti.yaml"
    pfad.write_text(text, encoding="utf-8")
    assert lade_buchhaltung(pfad).kontenrahmen == erwartet
    # DATEV-Stammdaten aus derselben Quelle
    mandant = lade_datev_mandant(pfad, date(2026, 1, 1), "1", "2")
    assert mandant.skr == erwartet[-2:]


def test_widerspruechlicher_kontenrahmen_ist_ein_fehler(tmp_path):
    from datetime import date

    from accounti.export.datev_stammdaten import lade_datev_mandant
    from accounti.konfiguration import lade_buchhaltung

    pfad = tmp_path / "accounti.yaml"
    pfad.write_text(
        "mandant:\n  kontenrahmen: SKR04\nbuchhaltung:\n  kontenrahmen: SKR03\n",
        encoding="utf-8",
    )
    with pytest.raises(KonfigurationError, match="widersprechen"):
        lade_buchhaltung(pfad)
    with pytest.raises(KonfigurationError, match="widersprechen"):
        lade_datev_mandant(pfad, date(2026, 1, 1), "1", "2")


def test_unbekannter_kontenrahmen_ist_ein_fehler(tmp_path):
    """Bisher fiel ein Tippfehler (SKR4) still auf SKR03 zurück."""
    from accounti.konfiguration import lade_buchhaltung

    pfad = tmp_path / "accounti.yaml"
    pfad.write_text("buchhaltung:\n  kontenrahmen: SKR4\n", encoding="utf-8")
    with pytest.raises(KonfigurationError, match="SKR03 oder SKR04"):
        lade_buchhaltung(pfad)


def test_fehlermeldung_nennt_den_richtigen_abschnitt(tmp_path):
    """Nachprüfung N5: Die Meldung setzte immer „mandant.“ vor das Feld — auch für
    Fehler unter ``buchhaltung`` und ``ustid_pruefung``."""
    from accounti.konfiguration import lade_buchhaltung, lade_ustid_pruefung

    pfad = tmp_path / "accounti.yaml"
    pfad.write_text("buchhaltung:\n  kontenrahmen: SKR4\n", encoding="utf-8")
    with pytest.raises(KonfigurationError) as fehler:
        lade_buchhaltung(pfad)
    assert "buchhaltung.kontenrahmen" in str(fehler.value)
    assert "mandant." not in str(fehler.value)
    # aus mandant.kontenrahmen übernommen: der Tippfehler steht dort
    pfad.write_text("mandant:\n  kontenrahmen: SKR4\n", encoding="utf-8")
    with pytest.raises(KonfigurationError, match=r"mandant\.kontenrahmen"):
        lade_buchhaltung(pfad)
    pfad.write_text("ustid_pruefung:\n  timeout_sekunden: -1\n", encoding="utf-8")
    with pytest.raises(KonfigurationError) as fehler:
        lade_ustid_pruefung(pfad)
    assert "ustid_pruefung.timeout_sekunden" in str(fehler.value)
    assert "mandant." not in str(fehler.value)


def test_vorlage_fuehrt_den_kontenrahmen_unter_buchhaltung():
    from pathlib import Path

    import yaml

    from accounti.konfiguration import lade_buchhaltung

    vorlage = Path(__file__).resolve().parents[1] / "config" / "accounti.example.yaml"
    daten = yaml.safe_load(vorlage.read_text(encoding="utf-8"))
    assert daten["buchhaltung"]["kontenrahmen"] == "SKR03"
    assert "kontenrahmen" not in daten["mandant"]
    assert lade_buchhaltung(vorlage).kontenrahmen == "SKR03"


# --- Baustein 10c P4, Schritt 5: neue und geänderte Felder (A44, A124) -------------


@pytest.mark.parametrize(
    "wert",
    ["'2026-07-01'", "'07-01'", "'01.07.'", "2025-07-01"],
    ids=["2026-07-01", "MM-TT", "TT.MM.", "date"],
)
def test_wirtschaftsjahr_tag_monat(tmp_path, wert):
    """``datev.wirtschaftsjahr_beginn`` als Tag und Monat: „MM-TT“, „TT.MM.“, ein Datum
    mit Jahr (das Jahr zählt nicht, N2) und das YAML-Datum; geschrieben „MM-TT“."""
    from accounti.abschluss.konfiguration import (
        TagMonat,
        lade_datev,
        lade_wirtschaftsjahr_beginn,
    )

    pfad = tmp_path / "accounti.yaml"
    pfad.write_text(f"datev:\n  wirtschaftsjahr_beginn: {wert}\n", encoding="utf-8")
    datev = lade_datev(pfad)
    assert datev.wirtschaftsjahr_beginn == TagMonat(7, 1)
    assert datev.wirtschaftsjahr_beginn.als_datum() == date(2000, 7, 1)
    assert datev.model_dump(mode="json")["wirtschaftsjahr_beginn"] == "07-01"
    assert lade_wirtschaftsjahr_beginn(pfad) == date(2000, 7, 1)
    assert TagMonat(2, 29).als_datum() == date(2000, 2, 29)  # Schaltjahr


@pytest.mark.parametrize("wert", ["'13-01'", "'31.02.'", "'Juli'", "7"])
def test_wirtschaftsjahr_ungueltig_nennt_pfad(tmp_path, wert):
    from accounti.abschluss.konfiguration import lade_datev, lade_wirtschaftsjahr_beginn

    pfad = tmp_path / "accounti.yaml"
    pfad.write_text(f"datev:\n  wirtschaftsjahr_beginn: {wert}\n", encoding="utf-8")
    for lader in (lade_datev, lade_wirtschaftsjahr_beginn):
        with pytest.raises(KonfigurationError) as fehler:
            lader(pfad)
        text = str(fehler.value)
        assert text.startswith(f"{pfad}: datev.wirtschaftsjahr_beginn"), text
        assert "MM-TT" in text, text


def test_datev_nummern_als_zahl_und_text(tmp_path):
    """N9: Eine Zahl aus der YAML wird wie bisher Text (führende Nullen gehen dabei
    verloren, die Vorlage schreibt Text); nur Ziffern."""
    from accounti.abschluss.konfiguration import lade_datev

    pfad = tmp_path / "accounti.yaml"
    pfad.write_text(
        "datev:\n  berater_nummer: 12345\n  mandanten_nummer: '00042'\n",
        encoding="utf-8",
    )
    datev = lade_datev(pfad)
    assert (datev.berater_nummer, datev.mandanten_nummer) == ("12345", "00042")
    assert datev.wirtschaftsjahr_beginn is None
    pfad.write_text("datev:\n  berater_nummer: '12a45'\n", encoding="utf-8")
    with pytest.raises(KonfigurationError, match=r"datev\.berater_nummer.*Ziffern"):
        lade_datev(pfad)
    assert lade_datev(tmp_path / "fehlt.yaml").berater_nummer is None


def test_rechtsform_und_kennfarbe(tmp_path):
    from accounti.konfiguration import lade_eigene_firma

    pfad = tmp_path / "accounti.yaml"
    pfad.write_text(VOLL, encoding="utf-8")
    firma = lade_firma(pfad)
    assert (firma.rechtsform, firma.kennfarbe, firma.sachkonten_laenge) == (
        None,
        None,
        4,
    )
    pfad.write_text(
        VOLL.replace(
            "  kuerzel: GM\n",
            "  kuerzel: GM\n  rechtsform: gmbh\n  kennfarbe: 3\n"
            "  sachkonten_laenge: 6\n",
        ),
        encoding="utf-8",
    )
    firma = lade_firma(pfad)
    assert (firma.rechtsform, firma.kennfarbe, firma.sachkonten_laenge) == (
        "gmbh",
        3,
        6,
    )
    pfad.write_text(VOLL.replace("  kuerzel: GM\n", "  rechtsform: kgaa\n"), "utf-8")
    with pytest.raises(KonfigurationError, match=r"mandant\.rechtsform"):
        lade_firma(pfad)
    # nachsichtig: die eigene Firma wird trotzdem erkannt
    eigene = lade_eigene_firma(pfad)
    assert eigene is not None and eigene.name == "Galerie Muster GmbH"


@pytest.mark.parametrize("farbe", [0, 7, "rot"])
def test_kennfarbe_ausserhalb_1_bis_6(tmp_path, farbe):
    pfad = tmp_path / "accounti.yaml"
    pfad.write_text(
        VOLL.replace("  kuerzel: GM\n", f"  kuerzel: GM\n  kennfarbe: {farbe}\n"),
        encoding="utf-8",
    )
    with pytest.raises(KonfigurationError, match=r"mandant\.kennfarbe"):
        lade_firma(pfad)


@pytest.mark.parametrize("laenge", [3, 9, 4.5, "true"])
def test_sachkonten_laenge_wie_der_datev_export(tmp_path, laenge):
    """``mandant.sachkonten_laenge`` ist Modellfeld (D16, M4) — mit derselben Grenze
    wie der DATEV-Export (4 bis 8, ``4.0`` gilt)."""
    from accounti.export.datev_stammdaten import sachkontenlaenge

    pfad = tmp_path / "accounti.yaml"
    zeile = f"  sachkonten_laenge: {laenge}\n"
    pfad.write_text(VOLL.replace("  kuerzel: GM\n", "  kuerzel: GM\n" + zeile), "utf-8")
    with pytest.raises(KonfigurationError, match=r"mandant\.sachkonten_laenge"):
        lade_firma(pfad)
    with pytest.raises(KonfigurationError, match=r"mandant\.sachkonten_laenge"):
        sachkontenlaenge(pfad)
    pfad.write_text(
        VOLL.replace("  kuerzel: GM\n", "  kuerzel: GM\n  sachkonten_laenge: 6.0\n"),
        encoding="utf-8",
    )
    assert lade_firma(pfad).sachkonten_laenge == 6 == sachkontenlaenge(pfad)


def test_pflichten_fehlerart_pflicht_fehlt_text_gleich(tmp_path):
    """M5: Ohne USt-IdNr. und Steuernummer ist die Fehlerart ``pflicht_fehlt`` (für
    „fehlt noch“, P4b) — der Text bleibt derselbe."""
    from pydantic import ValidationError

    from accounti.konfiguration import Firma

    pfad = tmp_path / "accounti.yaml"
    pfad.write_text(
        VOLL.replace("  ust_id: DE999999999\n", "").replace(
            '  steuernummer: "19/123/45678"\n', ""
        ),
        encoding="utf-8",
    )
    with pytest.raises(KonfigurationError) as fehler:
        lade_firma(pfad)
    assert "USt-IdNr. oder Steuernummer fehlt (§ 14 Abs. 4 Nr. 2 UStG)" in str(
        fehler.value
    )
    assert "Value error" not in str(fehler.value)
    with pytest.raises(ValidationError) as roh:
        Firma.model_validate(
            {
                "name": "X",
                "anschrift": {"strasse": "a", "plz": "1", "ort": "b"},
                "email": "x@x.example",
                "kontakt": {"name": "a", "telefon": "1", "email": "a@x.example"},
                "bank": {"iban": "DE89370400440532013000"},
            }
        )
    (eintrag,) = roh.value.errors()
    assert eintrag["type"] == "pflicht_fehlt"
    assert (
        eintrag["msg"] == "USt-IdNr. oder Steuernummer fehlt (§ 14 Abs. 4 Nr. 2 UStG)"
    )
    assert eintrag["ctx"] == {"felder": ["ust_id", "steuernummer"]}
