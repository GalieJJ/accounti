from decimal import Decimal

import pytest

from accounti.elster.konfiguration import (
    ElsterEinstellungen,
    KonfigurationError,
    bereiche,
    lade_elster,
)


def test_ohne_datei_und_ohne_abschnitt_gelten_standards(tmp_path):
    assert lade_elster(tmp_path / "fehlt.yaml") == ElsterEinstellungen()
    datei = tmp_path / "a.yaml"
    datei.write_text("mandant:\n  name: X\n", encoding="utf-8")
    e = lade_elster(datei)
    assert e.voranmeldungszeitraum == "monat"
    assert e.dauerfristverlaengerung is False
    assert e.uebermittler == "eric"
    assert e.eric.bibliothek is None
    assert e.abweichung_prozent == Decimal("50")


def test_abschnitt_wird_gelesen(tmp_path):
    datei = tmp_path / "a.yaml"
    datei.write_text(
        """
elster:
  voranmeldungszeitraum: quartal
  dauerfristverlaengerung: true
  bundesland: by
  finanzamt: {name: "Finanzamt München", iban: "DE89 3704 0044 0532 0130 00"}
  hersteller_id: "12345"
  kennziffern_konten: {"8150": 43}
  steuerrelevante_konten: ["8000-8999", "2700"]
  eric:
    bibliothek: /opt/eric/lib/libericapi.so
    zertifikat: /etc/accounti/elster.pfx
""",
        encoding="utf-8",
    )
    e = lade_elster(datei)
    assert e.voranmeldungszeitraum == "quartal"
    assert e.dauerfristverlaengerung is True
    assert e.bundesland == "BY"
    assert e.finanzamt.name == "Finanzamt München"
    assert e.finanzamt.iban == "DE89370400440532013000"
    assert e.kennziffern_konten == {"8150": 43}
    assert bereiche(e.steuerrelevante_konten) == ((8000, 8999), (2700, 2700))
    assert e.eric.zertifikat == "/etc/accounti/elster.pfx"


@pytest.mark.parametrize(
    "inhalt",
    [
        "elster:\n  bundesland: XX\n",
        "elster:\n  voranmeldungszeitraum: woche\n",
        "elster:\n  hersteller_id: 'abc'\n",
        "elster:\n  steuerrelevante_konten: ['8000-']\n",
        "elster:\n  kennziffern_konten: {'8150': 999}\n",
        "elster:\n  kennziffern_konten: {'1790': 83}\n",  # berechnet
        "elster:\n  kennziffern_konten: {'1781': 39}\n",  # aus der SVZ
        "elster:\n  kennziffern_konten: {'8150': 10}\n",  # Merker
        "elster:\n  sondervorauszahlung: 4000\n",  # ohne Jahr
    ],
)
def test_fehler_werden_benannt(tmp_path, inhalt):
    datei = tmp_path / "a.yaml"
    datei.write_text(inhalt, encoding="utf-8")
    with pytest.raises(KonfigurationError, match="elster"):
        lade_elster(datei)


def test_steuerkennziffern_und_sondervorauszahlung_je_jahr(tmp_path):
    datei = tmp_path / "a.yaml"
    datei.write_text(
        """
elster:
  kennziffern_konten: {"1588": 62, "3550": 91, "1782": 65}
  sondervorauszahlung: {2025: 5000, 2026: "4000.00"}
""",
        encoding="utf-8",
    )
    e = lade_elster(datei)
    assert e.kennziffern_konten == {"1588": 62, "3550": 91, "1782": 65}
    assert e.sondervorauszahlung == {2025: Decimal("5000"), 2026: Decimal("4000.00")}


def test_sondervorauszahlung_ohne_jahr_wird_erklaert(tmp_path):
    datei = tmp_path / "a.yaml"
    datei.write_text("elster:\n  sondervorauszahlung: 4000\n", encoding="utf-8")
    with pytest.raises(KonfigurationError, match="je Jahr"):
        lade_elster(datei)
