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
