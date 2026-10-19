import pytest

from accounti.konfiguration import KonfigurationError, lade_firma

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
