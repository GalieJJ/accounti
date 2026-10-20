import pytest

from accounti.bank.provider import BANK_PROVIDER, ProviderError
from accounti.models import Bankkonto
from tests.test_cli_opos import KOPF

ZEILEN = [
    "DE12;13.03.26;13.03.26;KARTENZAHLUNG;PARKHAUS ALTSTADT;APCOA;;;-5,00;EUR;gebucht",
    "DE12;13.03.26;13.03.26;KARTENZAHLUNG;PARKHAUS ALTSTADT;APCOA;;;-5,00;EUR;gebucht",
    "DE12;15.03.26;15.03.26;ENTGELT;Kontoführung März;Sparkasse;;;-5,90;EUR;gebucht",
]


def _konto(ordner, **einstellungen):
    return Bankkonto(
        iban="DE12",
        bezeichnung="Giro",
        provider="datei",
        einstellungen={"ordner": str(ordner), **einstellungen},
    )


def test_datei_provider_ist_registriert():
    provider = BANK_PROVIDER["datei"]
    assert provider.felder == ("ordner", "format")
    assert provider.geheime_felder == ()


def test_liest_alle_kontoauszuege_eines_ordners(tmp_path):
    (tmp_path / "maerz-1.csv").write_text(
        "\n".join([KOPF, *ZEILEN[:2]]) + "\n", encoding="utf-8"
    )
    (tmp_path / "maerz-2.CSV").write_text(
        "\n".join([KOPF, ZEILEN[2]]) + "\n", encoding="utf-8"
    )
    (tmp_path / "notiz.txt").write_text("kein Kontoauszug", encoding="utf-8")
    abruf = BANK_PROVIDER["datei"]().abrufen(_konto(tmp_path), {}, None)
    assert [str(t.betrag) for t in abruf.transaktionen] == ["-5.00", "-5.00", "-5.90"]
    assert abruf.transaktionen[0].gegenkonto_name == "APCOA"


def test_festes_format(tmp_path):
    (tmp_path / "a.csv").write_text("\n".join([KOPF, ZEILEN[0]]) + "\n", "utf-8")
    abruf = BANK_PROVIDER["datei"]().abrufen(
        _konto(tmp_path, format="sparkasse"), {}, None
    )
    assert len(abruf.transaktionen) == 1


@pytest.mark.parametrize(
    ("einstellungen", "grund"),
    [({"ordner": "/gibt/es/nicht"}, "Ordner"), ({}, "Ordner")],
)
def test_fehlender_ordner(einstellungen, grund):
    konto = Bankkonto(iban="DE12", bezeichnung="x", einstellungen=einstellungen)
    with pytest.raises(ProviderError, match=grund):
        BANK_PROVIDER["datei"]().abrufen(konto, {}, None)


def test_unlesbare_datei_nennt_den_namen(tmp_path):
    (tmp_path / "kaputt.csv").write_text("irgendwas;ohne;kopf\n1;2;3\n", "utf-8")
    with pytest.raises(ProviderError, match="kaputt.csv"):
        BANK_PROVIDER["datei"]().abrufen(_konto(tmp_path), {}, None)
