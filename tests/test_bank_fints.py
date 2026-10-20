"""FinTS-Provider gegen die Attrappe des python-fints-Clients — nie gegen eine Bank."""

import base64
import json
from datetime import date, timedelta
from decimal import Decimal

import pytest
import requests
from fints.exceptions import FinTSConnectionError

from accounti.bank import fints as fints_modul
from accounti.bank.einstellungen import FinTSEinstellungen
from accounti.bank.fints import SITZUNG, FinTSProvider, TanVerfahren, richte_fints_ein
from accounti.bank.lauf import rufe_ab
from accounti.bank.provider import (
    BANK_PROVIDER,
    FreigabeNoetigError,
    ProviderError,
)
from accounti.bank.tresor import neuer_schluessel, verschluessele
from accounti.db import init_db, session_factory
from accounti.db.repository import (
    lade_bankkonten,
    lade_transaktionen,
    speichere_bankkonto,
)
from accounti.models import Bankkonto, KontoZustand
from tests.fints_attrappe import IBAN, AttrappenBank

PRODUKT_ID = "TESTPRODUKT0815"
ZUGANG = {"benutzerkennung": "kunde-4711", "pin": "1234"}
HEUTE = date.today()


@pytest.fixture
def bank(monkeypatch):
    bank = AttrappenBank()
    monkeypatch.setattr(fints_modul, "erzeuge_client", bank.fabrik)
    monkeypatch.delenv("ACCOUNTI_FINTS_PRODUKT_ID", raising=False)
    return bank


def _konto(**einstellungen):
    return Bankkonto(
        iban=IBAN,
        bezeichnung="Giro AttrappenBank",
        provider="fints",
        einstellungen={
            "blz": "12030000",
            "server": "https://fints.example.invalid/fints30",
            **einstellungen,
        },
    )


class Uhr:
    def __init__(self):
        self.jetzt = 0.0
        self.gewartet: list[float] = []

    def __call__(self):
        return self.jetzt

    def warte(self, sekunden):
        self.gewartet.append(sekunden)
        self.jetzt += max(sekunden, 1)


def _provider(freigabe=None, uhr=None, **einstellungen):
    uhr = uhr or Uhr()
    werte = {"produkt_id": PRODUKT_ID, "freigabe_intervall_sekunden": 2}
    werte.update(einstellungen)
    return FinTSProvider(
        freigabe,
        einstellungen=FinTSEinstellungen(**werte),
        warte=uhr.warte,
        uhr=uhr,
    )


def _sitzung(zugang):
    return json.loads(base64.b64decode(zugang[SITZUNG]))


class Rueckfrage:
    def __init__(self, *antworten):
        self.antworten = list(antworten)
        self.anfragen = []

    def __call__(self, anfrage):
        self.anfragen.append(anfrage)
        return self.antworten.pop(0)


def test_registriert():
    klasse = BANK_PROVIDER["fints"]
    assert klasse.geheime_felder == ("benutzerkennung", "pin")
    assert {"blz", "server", "format", "produkt_id", "tan_verfahren"} <= set(
        klasse.felder
    )


def test_ohne_produkt_id_kein_abruf(bank):
    with pytest.raises(ProviderError, match="Produkt-ID") as fehler:
        _provider(produkt_id=None).abrufen(_konto(), ZUGANG, None)
    assert "ACCOUNTI_FINTS_PRODUKT_ID" in str(fehler.value)
    assert "Registrierung" in str(fehler.value)
    assert bank.clients == []


def test_produkt_id_am_konto_geht_vor(bank):
    bank.sca_bei_init = None
    _provider().abrufen(_konto(produkt_id="AMKONTO"), ZUGANG, None)
    assert bank.clients[-1]["produkt_id"] == "AMKONTO"
    _provider().abrufen(_konto(), ZUGANG, None)
    assert bank.clients[-1]["produkt_id"] == PRODUKT_ID
    assert bank.clients[-1]["produkt_version"] == "0.1"


def test_produkt_id_aus_der_umgebung(bank, monkeypatch, tmp_path):
    bank.sca_bei_init = None
    monkeypatch.setenv("ACCOUNTI_FINTS_PRODUKT_ID", "AUSUMGEBUNG")
    monkeypatch.chdir(tmp_path)  # keine config/accounti.yaml
    FinTSProvider(warte=lambda s: None).abrufen(_konto(), ZUGANG, None)
    assert bank.clients[-1]["produkt_id"] == "AUSUMGEBUNG"


def test_camt_bevorzugt_ohne_freigabe(bank):
    bank.sca_bei_init = None
    abruf = _provider().abrufen(_konto(), ZUGANG, None)
    (tx,) = abruf.transaktionen  # der Vormerkposten zählt nicht
    assert (tx.betrag, tx.quelle_referenz) == (Decimal("-25.00"), "2026031900011")
    assert bank.abrufe == [("camt", IBAN, HEUTE - timedelta(days=90), None)]
    assert bank.clients[-1]["benutzerkennung"] == "kunde-4711"
    assert bank.clients[-1]["blz"] == "12030000"
    assert bank.clients[-1]["daten"] is None
    assert abruf.zugang is not None
    assert abruf.zugang["pin"] == "1234"
    assert _sitzung(abruf.zugang)["system_id"] == "SYS-1"


def test_mt940_wenn_die_bank_kein_camt_kennt(bank):
    bank.sca_bei_init, bank.camt = None, False
    abruf = _provider().abrufen(_konto(), ZUGANG, date(2026, 3, 1))
    assert len(abruf.transaktionen) == 6
    assert (abruf.saldo, abruf.saldo_datum) == (Decimal("2167.10"), date(2026, 3, 31))
    assert bank.abrufe == [("mt940", IBAN, date(2026, 3, 1), None)]


def test_format_einstellung(bank):
    bank.sca_bei_init = None
    _provider().abrufen(_konto(format="mt940"), ZUGANG, None)
    assert bank.abrufe[-1][0] == "mt940"
    bank.camt = False
    with pytest.raises(ProviderError, match="camt"):
        _provider().abrufen(_konto(format="camt"), ZUGANG, None)
    with pytest.raises(ProviderError, match="format"):
        _provider().abrufen(_konto(format="pdf"), ZUGANG, None)


def test_freigabe_ohne_rueckfrage_wird_zum_zustand(bank):
    with pytest.raises(FreigabeNoetigError) as fehler:
        _provider().abrufen(_konto(), ZUGANG, None)
    assert "accounti fints freigeben" in str(fehler.value)
    assert IBAN in str(fehler.value)
    # die Sitzung (Kundensystem-ID) wird trotzdem gesichert
    assert fehler.value.zugang is not None
    assert _sitzung(fehler.value.zugang)["system_id"] == "SYS-1"
    assert bank.abrufe == []


def test_freigabe_mit_tan_und_danach_ohne_eingabe(bank):
    """Akzeptanz 1 am Provider: nach der Freigabe holt der nächste Abruf ohne
    Eingabe — mit derselben Kundensystem-ID, die Bank kennt die Freigabe."""
    frage = Rueckfrage("123456")
    abruf = _provider(frage).abrufen(_konto(), ZUGANG, None)
    assert len(abruf.transaktionen) == 1
    (anfrage,) = frage.anfragen
    assert (anfrage.text, anfrage.app, anfrage.konto.iban) == (
        "Bitte TAN eingeben",
        False,
        IBAN,
    )
    assert bank.tans == ["123456"]

    zweiter = _provider().abrufen(_konto(), abruf.zugang, HEUTE)
    assert len(zweiter.transaktionen) == 1
    assert bank.systeme == 1  # keine neue Kundensystem-ID
    assert bank.clients[-1]["daten"] is not None


def test_freigabe_in_der_app_mit_statusabfrage(bank):
    bank.sca_bei_init, bank.app_bestaetigt_nach = "app", 3
    uhr = Uhr()
    frage = Rueckfrage("")
    abruf = _provider(frage, uhr=uhr).abrufen(_konto(), ZUGANG, None)
    assert len(abruf.transaktionen) == 1
    assert frage.anfragen[0].app is True
    assert uhr.gewartet == [2, 2, 2]
    assert bank.tans == []


def test_freigabe_in_der_app_nicht_rechtzeitig(bank):
    bank.sca_bei_init, bank.app_bestaetigt_nach = "app", 1000
    uhr = Uhr()
    with pytest.raises(FreigabeNoetigError, match="nicht rechtzeitig"):
        _provider(Rueckfrage(""), uhr=uhr, freigabe_wartezeit_sekunden=10).abrufen(
            _konto(), ZUGANG, None
        )
    assert 4 <= len(uhr.gewartet) <= 6


def test_rueckfrage_abgebrochen(bank):
    with pytest.raises(FreigabeNoetigError, match="abgebrochen"):
        _provider(Rueckfrage(None)).abrufen(_konto(), ZUGANG, None)


def test_tan_fuer_den_umsatzabruf(bank):
    bank.sca_bei_init, bank.sca_beim_abruf = None, True
    with pytest.raises(FreigabeNoetigError):
        _provider().abrufen(_konto(), ZUGANG, None)
    frage = Rueckfrage("123456")
    abruf = _provider(frage).abrufen(_konto(), ZUGANG, None)
    assert len(abruf.transaktionen) == 1
    assert frage.anfragen[0].text == "TAN für den Umsatzabruf"


def test_falsche_tan(bank):
    with pytest.raises(ProviderError, match="9941"):
        _provider(Rueckfrage("000000")).abrufen(_konto(), ZUGANG, None)


def test_falsche_pin_ohne_wiederholung_und_ohne_geheimnisse(bank):
    zugang = {"benutzerkennung": "kunde-4711", "pin": "falsch-0815"}
    with pytest.raises(ProviderError, match="PIN") as fehler:
        _provider(Rueckfrage("123456")).abrufen(_konto(), zugang, None)
    assert "falsch-0815" not in str(fehler.value)
    assert "sperren" in str(fehler.value)
    assert len(bank.clients) == 1


@pytest.mark.parametrize(
    "fehler",
    [
        FinTSConnectionError("Bad status code 503"),
        requests.ConnectionError("Name or service not known"),
    ],
)
def test_bank_nicht_erreichbar(bank, fehler):
    bank.verbindung_weg = fehler
    with pytest.raises(ProviderError, match="nicht erreichbar"):
        _provider().abrufen(_konto(), ZUGANG, None)


def test_geheimnisse_werden_aus_meldungen_entfernt(bank):
    bank.verbindung_weg = FinTSConnectionError("Antwort für kunde-4711 mit 1234")
    with pytest.raises(ProviderError) as fehler:
        _provider().abrufen(_konto(), ZUGANG, None)
    assert "kunde-4711" not in str(fehler.value)
    assert "1234" not in str(fehler.value)


def test_konto_gibt_es_unter_dem_zugang_nicht(bank):
    bank.sca_bei_init, bank.konten = None, ["DE89370400440532013000"]
    with pytest.raises(ProviderError, match=IBAN) as fehler:
        _provider().abrufen(_konto(), ZUGANG, None)
    assert "DE89370400440532013000" in str(fehler.value)


@pytest.mark.parametrize(
    ("konto", "zugang", "grund"),
    [
        (_konto(blz=""), ZUGANG, "blz"),
        (_konto(server=""), ZUGANG, "server"),
        (_konto(), {"pin": "1234"}, "benutzerkennung"),
        (_konto(), {"benutzerkennung": "x"}, "pin"),
    ],
)
def test_unvollstaendige_einrichtung(bank, konto, zugang, grund):
    with pytest.raises(ProviderError, match=grund):
        _provider().abrufen(konto, zugang, None)


def test_tan_verfahren_und_medium_aus_den_einstellungen(bank):
    bank.sca_bei_init = None
    abruf = _provider().abrufen(
        _konto(tan_verfahren="942", tan_medium="Handy"), ZUGANG, None
    )
    assert _sitzung(abruf.zugang) == {
        "system_id": "SYS-1",
        "verfahren": "942",
        "medium": "Handy",
    }


def test_kaputte_sitzung_wird_verworfen(bank):
    bank.sca_bei_init = None
    _provider().abrufen(_konto(), {**ZUGANG, SITZUNG: "kein base64 %%%"}, None)
    assert bank.clients[-1]["daten"] is None


# --- Einrichtung -------------------------------------------------------------


def test_einrichtung_waehlt_verfahren_und_medium_und_gibt_frei(bank):
    bank.medien = ["Handy A", "Handy B"]
    gesehen = {}

    def waehle_verfahren(verfahren):
        gesehen["verfahren"] = verfahren
        return "942"

    def waehle_medium(medien):
        gesehen["medien"] = medien
        return "Handy B"

    konto, zugang = richte_fints_ein(
        _konto(),
        ZUGANG,
        waehle_verfahren=waehle_verfahren,
        waehle_medium=waehle_medium,
        freigabe=Rueckfrage("123456"),
        einstellungen=FinTSEinstellungen(produkt_id=PRODUKT_ID),
    )
    assert gesehen["verfahren"] == [
        TanVerfahren("921", "pushTAN 2.0"),
        TanVerfahren("942", "mobileTAN"),
    ]
    assert gesehen["medien"] == ["Handy A", "Handy B"]
    assert konto.einstellungen["tan_verfahren"] == "942"
    assert konto.einstellungen["tan_medium"] == "Handy B"
    assert _sitzung(zugang)["system_id"] in bank.freigegeben
    assert bank.abrufe == []  # Einrichten holt noch keine Umsätze


def test_einrichtung_mit_nur_einem_verfahren_fragt_nicht(bank):
    bank.verfahren = {"921": "pushTAN 2.0"}
    bank.sca_bei_init = None

    def nie(_):
        raise AssertionError("keine Rückfrage erwartet")

    konto, _ = richte_fints_ein(
        _konto(),
        ZUGANG,
        waehle_verfahren=nie,
        waehle_medium=nie,
        freigabe=nie,
        einstellungen=FinTSEinstellungen(produkt_id=PRODUKT_ID),
    )
    assert konto.einstellungen["tan_verfahren"] == "921"
    assert "tan_medium" not in konto.einstellungen


def test_einrichtung_scheitert_wenn_das_konto_fehlt(bank):
    bank.sca_bei_init, bank.konten = None, ["DE89370400440532013000"]
    with pytest.raises(ProviderError, match=IBAN):
        richte_fints_ein(
            _konto(),
            ZUGANG,
            waehle_verfahren=lambda v: v[0].kennung,
            waehle_medium=lambda m: m[0],
            freigabe=Rueckfrage("123456"),
            einstellungen=FinTSEinstellungen(produkt_id=PRODUKT_ID),
        )


# --- Über den Abruf aller Konten (Tresor, Zustand) -------------------------------


@pytest.fixture
def make_session(tmp_path):
    engine, factory = session_factory(f"sqlite:///{tmp_path / 'f.db'}")
    init_db(engine)
    yield factory
    engine.dispose()


def test_abruf_aller_konten_mit_freigabe_und_tresor(
    bank, make_session, tmp_path, monkeypatch
):
    """Akzeptanz 1 und 5: Freigabe einmal, danach ohne Eingabe; nichts im Klartext."""
    monkeypatch.setenv("ACCOUNTI_FINTS_PRODUKT_ID", PRODUKT_ID)
    schluessel = neuer_schluessel()
    konto = _konto()
    konto = konto.model_copy(
        update={"zugang": verschluessele(ZUGANG, schluessel, str(konto.id))}
    )
    with make_session() as s:
        speichere_bankkonto(s, konto)
        s.commit()

    def lauf(**kw):
        with make_session() as s:
            (ergebnis,) = rufe_ab(s, schluessel, **kw)
            s.commit()
        return ergebnis

    erster = lauf()  # Cron: keine Rückfrage → Zustand
    assert erster.zustand is KontoZustand.FREIGABE_NOETIG
    assert "accounti fints freigeben" in (erster.meldung or "")
    zweiter = lauf(freigabe=Rueckfrage("123456"))
    assert (zweiter.zustand, zweiter.neu) == (KontoZustand.BEREIT, 1)
    dritter = lauf()  # ohne Eingabe
    assert (dritter.zustand, dritter.neu, dritter.doppelt) == (
        KontoZustand.BEREIT,
        0,
        1,
    )
    assert bank.systeme == 1
    with make_session() as s:
        assert len(lade_transaktionen(s)) == 1
        (gespeichert,) = lade_bankkonten(s)
    assert gespeichert.zustand is KontoZustand.BEREIT
    roh = (tmp_path / "f.db").read_bytes()
    for geheim in (b"kunde-4711", b"SYS-1", PRODUKT_ID.encode()):
        assert geheim not in roh
