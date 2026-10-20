from datetime import date, datetime
from decimal import Decimal

import pytest

from accounti.bank.lauf import bank_lauf, rufe_ab, speichere_neue
from accounti.bank.provider import (
    BANK_PROVIDER,
    Abruf,
    BankProvider,
    FreigabeNoetigError,
    ProviderError,
)
from accounti.bank.tresor import neuer_schluessel, verschluessele
from accounti.buchung.mit_beleg import kontiere_mit_beleg
from accounti.db import init_db, session_factory
from accounti.db.repository import (
    lade_bankkonten,
    lade_buchungen,
    lade_transaktionen,
    speichere_bankkonto,
)
from accounti.klassifikation.engine import KlassifikationsEngine, RegelwerkEngine
from accounti.konfiguration import Buchhaltung
from accounti.models import Bankkonto, KontoZustand
from tests.test_bank_abgleich import quittung, umsatz
from tests.test_buchung_mit_beleg import TANKEN

SCHLUESSEL = neuer_schluessel()
EINSTELLUNGEN = Buchhaltung()


class Attrappe(BankProvider):
    """Liefert vorbereitete Umsätze; merkt sich Zugang und Abrufstand."""

    name = "attrappe"
    felder = ("bank",)
    geheime_felder = ("pin",)
    antworten: dict[str, object] = {}
    gesehen: list[tuple[str, dict[str, str], date | None]] = []

    def abrufen(self, konto, zugang, ab):
        Attrappe.gesehen.append((konto.iban, zugang, ab))
        antwort = Attrappe.antworten[konto.iban]
        if isinstance(antwort, Exception):
            raise antwort
        return antwort


@pytest.fixture(autouse=True)
def attrappe():
    BANK_PROVIDER["attrappe"] = Attrappe
    Attrappe.antworten, Attrappe.gesehen = {}, []
    yield
    del BANK_PROVIDER["attrappe"]


@pytest.fixture
def make_session(tmp_path):
    engine, factory = session_factory(f"sqlite:///{tmp_path / 'l.db'}")
    init_db(engine)
    yield factory
    engine.dispose()


def _konto(make_session, iban="DE12", sachkonto="1200", pin="4711", **kw):
    k = Bankkonto(
        iban=iban, bezeichnung=f"Konto {iban}", sachkonto=sachkonto, provider="attrappe"
    )
    k = k.model_copy(
        update={"zugang": verschluessele({"pin": pin}, SCHLUESSEL, str(k.id)), **kw}
    )
    with make_session() as s:
        speichere_bankkonto(s, k)
        s.commit()
    return k


def _abruf(make_session, **kw):
    with make_session() as s:
        ergebnis = rufe_ab(s, SCHLUESSEL, **kw)
        s.commit()
    return ergebnis


def test_abruf_ohne_weitere_eingabe_und_ohne_dubletten(make_session):
    """Akzeptanz 1 (mit Attrappe) und 2."""
    konto = _konto(make_session)
    Attrappe.antworten["DE12"] = Abruf([umsatz(), umsatz(), umsatz(betrag="-7")])
    (erster,) = _abruf(make_session)
    assert (erster.neu, erster.doppelt, erster.zustand) == (3, 0, KontoZustand.BEREIT)
    assert Attrappe.gesehen == [("DE12", {"pin": "4711"}, None)]

    (zweiter,) = _abruf(make_session, jetzt=datetime(2026, 3, 20, 8, 0))
    assert (zweiter.neu, zweiter.doppelt) == (0, 3)
    assert Attrappe.gesehen[-1][2] == date(2026, 2, 27)  # Stand 13.03. minus 14 Tage
    with make_session() as s:
        transaktionen = lade_transaktionen(s)
        (gespeichert,) = lade_bankkonten(s)
    assert len(transaktionen) == 3
    assert all(
        t.bankkonto_id == konto.id and t.sachkonto == "1200" for t in transaktionen
    )
    assert gespeichert.abrufstand == date(2026, 3, 13)
    assert gespeichert.letzter_abruf == datetime(2026, 3, 20, 8, 0)


def test_kein_zugang_im_klartext_in_der_datenbank(make_session, tmp_path):
    """Akzeptanz 5."""
    _konto(make_session, pin="sehr-geheime-pin-0815")
    roh = (tmp_path / "l.db").read_bytes()
    assert b"sehr-geheime-pin-0815" not in roh
    assert "sehr-geheime-pin-0815".encode("utf-16-le") not in roh


def test_freigabe_noetig_ist_ein_zustand_und_haelt_andere_nicht_auf(make_session):
    _konto(make_session, iban="DE12")
    _konto(make_session, iban="DE34")
    Attrappe.antworten["DE12"] = FreigabeNoetigError("TAN-Freigabe in der App nötig")
    Attrappe.antworten["DE34"] = Abruf([umsatz()])
    eins, zwei = _abruf(make_session)
    assert (eins.zustand, eins.neu) == (KontoZustand.FREIGABE_NOETIG, 0)
    assert "TAN" in (eins.meldung or "")
    assert (zwei.zustand, zwei.neu) == (KontoZustand.BEREIT, 1)
    with make_session() as s:
        zustaende = {k.iban: k.zustand for k in lade_bankkonten(s)}
    assert zustaende == {
        "DE12": KontoZustand.FREIGABE_NOETIG,
        "DE34": KontoZustand.BEREIT,
    }


def test_providerfehler_und_falscher_schluessel(make_session):
    _konto(make_session, iban="DE12")
    _konto(make_session, iban="DE34", provider="gibtsnicht")
    Attrappe.antworten["DE12"] = ProviderError("Bank nicht erreichbar")
    eins, zwei = _abruf(make_session)
    assert eins.zustand is KontoZustand.FEHLER and "erreichbar" in (eins.meldung or "")
    assert zwei.zustand is KontoZustand.FEHLER and "gibtsnicht" in (zwei.meldung or "")
    with make_session() as s:
        (falsch,) = rufe_ab(s, neuer_schluessel(), konten=[lade_bankkonten(s)[0]])
    assert falsch.zustand is KontoZustand.FEHLER
    assert "entschlüsselt" in (falsch.meldung or "")


def test_dateiimport_bleibt_nutzbar_wenn_der_provider_ausfaellt(make_session):
    """Akzeptanz 6: speichere_neue ist derselbe Weg wie 'import bank'."""
    _konto(make_session)
    Attrappe.antworten["DE12"] = ProviderError("Wartung")
    _abruf(make_session)
    with make_session() as s:
        assert speichere_neue(s, [umsatz(), umsatz()], "DE12") == (2, 0)
        assert speichere_neue(s, [umsatz(), umsatz()], "DE12") == (0, 2)
        s.commit()
        assert len(lade_transaktionen(s)) == 2


def test_lauf_ruft_ab_gleicht_ab_und_kontiert_gegen_das_sachkonto(make_session):
    _konto(make_session, iban="DE34", sachkonto="1210")
    b = quittung(netto=Decimal("50.00"), steuer=Decimal("9.50"))
    from accounti.db.repository import speichere_beleg

    with make_session() as s:
        speichere_beleg(s, b)
        s.commit()
    Attrappe.antworten["DE34"] = Abruf(
        [umsatz(), umsatz(betrag="-20.00", gegenkonto_name="ARAL", tag=2)]
    )
    engine = KlassifikationsEngine(regelwerk=RegelwerkEngine([TANKEN]))
    with make_session() as s:
        ergebnis = bank_lauf(s, engine, EINSTELLUNGEN, SCHLUESSEL)
        s.commit()
    assert ergebnis.abrufe[0].neu == 2
    assert len(ergebnis.abgleich.automatisch) == 1
    assert (ergebnis.kontierung.kontiert, ergebnis.kontierung.mit_beleg) == (2, 1)
    with make_session() as s:
        buchungen = lade_buchungen(s)
    assert {(b.soll_konto, b.haben_konto) for b in buchungen} == {("4530", "1210")}

    with make_session() as s:  # zweiter Lauf: nichts Neues, nichts doppelt
        zweiter = bank_lauf(s, engine, EINSTELLUNGEN, SCHLUESSEL)
        s.commit()
        assert len(lade_buchungen(s)) == 2
    assert (zweiter.abrufe[0].neu, zweiter.kontierung.kontiert) == (0, 0)


def test_kontierung_mit_beleg_nutzt_das_sachkonto_des_umsatzes():
    tx = umsatz().model_copy(update={"sachkonto": "1800"})
    (x,) = kontiere_mit_beleg(
        tx,
        quittung(netto=Decimal("50.00"), steuer=Decimal("9.50")),
        EINSTELLUNGEN,
        RegelwerkEngine([TANKEN]),
    )
    assert (x.soll_konto, x.haben_konto) == ("4530", "1800")
