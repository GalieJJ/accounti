import pytest

from accounti.bank.einstellungen import (
    BankEinstellungen,
    KreditkartenEinstellungen,
    lade_bank_einstellungen,
)
from accounti.konfiguration import KonfigurationError


@pytest.fixture(autouse=True)
def ohne_produkt_id(monkeypatch):
    monkeypatch.delenv("ACCOUNTI_FINTS_PRODUKT_ID", raising=False)


def _schreibe(tmp_path, text):
    pfad = tmp_path / "accounti.yaml"
    pfad.write_text(text, encoding="utf-8")
    return pfad


def test_ohne_datei_und_ohne_abschnitt_gelten_die_standards(tmp_path):
    for pfad in (tmp_path / "fehlt.yaml", _schreibe(tmp_path, "mandant: {}\n")):
        e = lade_bank_einstellungen(pfad)
        assert e == BankEinstellungen()
    assert e.fints.produkt_id is None
    assert e.fints.erster_abruf_tage == 90
    assert e.kreditkarte.belastung_fenster_tage == 30


def test_abschnitt_wird_gelesen(tmp_path):
    pfad = _schreibe(
        tmp_path,
        "bank:\n  fints:\n    produkt_id: ABC123\n    freigabe_wartezeit_sekunden: 60\n"
        "  kreditkarte:\n    geldtransit_konto: '1361'\n",
    )
    e = lade_bank_einstellungen(pfad)
    assert e.fints.produkt_id == "ABC123"
    assert e.fints.freigabe_wartezeit_sekunden == 60
    assert e.kreditkarte.geldtransit("SKR03") == "1361"


def test_produkt_id_aus_der_umgebung(tmp_path, monkeypatch):
    pfad = _schreibe(tmp_path, "bank:\n  fints:\n    produkt_id: AUSDATEI\n")
    monkeypatch.setenv("ACCOUNTI_FINTS_PRODUKT_ID", "AUSUMGEBUNG")
    assert lade_bank_einstellungen(pfad).fints.produkt_id == "AUSUMGEBUNG"


def test_platzhalter_fuer_umgebungsvariablen(tmp_path, monkeypatch):
    pfad = _schreibe(tmp_path, "bank:\n  fints:\n    produkt_id: '${MEINE_ID}'\n")
    assert lade_bank_einstellungen(pfad).fints.produkt_id is None  # nicht gesetzt
    monkeypatch.setenv("MEINE_ID", "XYZ")
    assert lade_bank_einstellungen(pfad).fints.produkt_id == "XYZ"


@pytest.mark.parametrize(
    ("text", "grund"),
    [
        ("bank:\n  fints:\n    produkt_id: '" + "A" * 26 + "'\n", "25"),
        ("bank:\n  fints:\n    produkt_version: '1.2.3.4'\n", "produkt_version"),
        ("bank:\n  fints:\n    erster_abruf_tage: 0\n", "erster_abruf_tage"),
        ("bank:\n  kreditkarte:\n    belastung_muster: '(kaputt'\n", "Muster"),
        ("bank: [1, 2]\n", "bank"),
    ],
)
def test_fehler_nennen_den_abschnitt(tmp_path, text, grund):
    with pytest.raises(KonfigurationError, match="bank") as fehler:
        lade_bank_einstellungen(_schreibe(tmp_path, text))
    assert grund in str(fehler.value)


def test_geldtransit_nach_kontenrahmen():
    k = KreditkartenEinstellungen()
    assert (k.geldtransit("SKR03"), k.geldtransit("skr04")) == ("1360", "1460")


@pytest.mark.parametrize(
    ("text", "belastung", "ausgleich"),
    [
        ("KREDITKARTENABRECHNUNG 03/26 XXXX 1234", True, False),
        ("VISA Firmenkarte Abrechnung", True, False),
        ("Lastschrift American Express", True, True),
        ("Ihre Zahlung - Danke", False, True),
        ("Saldenausgleich durch Lastschrift", False, True),
        ("Gutschrift Amazon Retoure", False, False),
        ("Kartenzahlung Tankstelle", False, False),
    ],
)
def test_standardmuster(text, belastung, ausgleich):
    k = KreditkartenEinstellungen()
    assert k.ist_belastung(text) is belastung
    assert k.ist_ausgleich(text) is ausgleich
