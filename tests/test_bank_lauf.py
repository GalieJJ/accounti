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
    ZugangAbgelehntError,
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


def test_freigabe_noetig_wird_ohne_rueckfrage_nicht_erneut_angefragt(make_session):
    """Jeder Abruf öffnet bei der Bank einen Dialog und löst eine neue
    Freigabe-Anforderung aus (Push, SMS), die niemand bestätigen kann — der Cron
    wartet deshalb auf `accounti fints freigeben`."""
    _konto(make_session)
    Attrappe.antworten["DE12"] = FreigabeNoetigError("Bitte in der App freigeben")
    _abruf(make_session, jetzt=datetime(2026, 3, 20, 8, 0))
    (zweiter,) = _abruf(make_session, jetzt=datetime(2026, 3, 20, 12, 0))
    (dritter,) = _abruf(make_session)
    assert len(Attrappe.gesehen) == 1
    assert dritter.zustand is KontoZustand.FREIGABE_NOETIG and dritter.uebersprungen
    assert "Bitte in der App freigeben" in (dritter.meldung or "")
    with make_session() as s:
        (konto,) = lade_bankkonten(s)
    assert konto.letzter_abruf == datetime(2026, 3, 20, 8, 0)  # nichts versucht
    assert konto.meldung == "Bitte in der App freigeben"

    Attrappe.antworten["DE12"] = Abruf([umsatz()])
    (frei,) = _abruf(make_session, freigabe=lambda anfrage: "123456")
    assert (frei.zustand, frei.neu, frei.uebersprungen) == (
        KontoZustand.BEREIT,
        1,
        False,
    )
    assert len(Attrappe.gesehen) == 2
    (danach,) = _abruf(make_session)  # wieder bereit: der Cron ruft ab
    assert (danach.zustand, len(Attrappe.gesehen)) == (KontoZustand.BEREIT, 3)


def test_abgelehnter_zugang_wird_ohne_rueckfrage_nicht_wiederholt(make_session):
    """PIN falsch oder Zugang gesperrt: jeder weitere Anmeldeversuch kann den
    Zugang bei der Bank sperren — erst ein erneuerter Zugang wird wieder versucht."""
    _konto(make_session)
    _konto(make_session, iban="DE34")
    Attrappe.antworten["DE12"] = ZugangAbgelehntError("Die Bank lehnt die PIN ab")
    Attrappe.antworten["DE34"] = Abruf([umsatz()])
    eins, zwei = _abruf(make_session)
    assert eins.zustand is KontoZustand.ZUGANG_ABGELEHNT
    assert zwei.zustand is KontoZustand.BEREIT
    _abruf(make_session)
    eins, zwei = _abruf(make_session)
    assert [iban for iban, _, _ in Attrappe.gesehen].count("DE12") == 1
    assert [iban for iban, _, _ in Attrappe.gesehen].count("DE34") == 3
    assert eins.uebersprungen and "PIN" in (eins.meldung or "")
    with make_session() as s:
        zustaende = {k.iban: k.zustand for k in lade_bankkonten(s)}
    assert zustaende["DE12"] is KontoZustand.ZUGANG_ABGELEHNT


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


class Sitzungsbank(BankProvider):
    """Gibt eine aktualisierte Sitzung zurück (wie FinTS) und merkt sich die
    Rückfrage, mit der er erzeugt wurde."""

    name = "sitzungsbank"
    geheime_felder = ("pin",)
    erzeugt: list[object] = []
    freigabe_noetig = False

    def __init__(self, freigabe=None):
        super().__init__(freigabe)
        Sitzungsbank.erzeugt.append(freigabe)

    def abrufen(self, konto, zugang, ab):
        neu = {**zugang, "sitzung": zugang.get("sitzung", "geheime-sitzung") + "+"}
        if Sitzungsbank.freigabe_noetig:
            raise FreigabeNoetigError("Bitte freigeben", zugang=neu)
        return Abruf([umsatz()], zugang=neu)


@pytest.fixture
def sitzungsbank():
    BANK_PROVIDER["sitzungsbank"] = Sitzungsbank
    Sitzungsbank.erzeugt, Sitzungsbank.freigabe_noetig = [], False
    yield
    del BANK_PROVIDER["sitzungsbank"]


def _zugang(make_session):
    from accounti.bank.tresor import entschluessele

    with make_session() as s:
        (k,) = lade_bankkonten(s)
    return entschluessele(k.zugang, SCHLUESSEL, str(k.id)), k


def test_rueckfrage_wird_an_den_provider_gereicht(make_session, sitzungsbank):
    _konto(make_session, provider="sitzungsbank")

    def frage(anfrage):
        return "123456"

    _abruf(make_session)
    _abruf(make_session, freigabe=frage)
    assert Sitzungsbank.erzeugt == [None, frage]


def test_geaenderter_zugang_wird_neu_verschluesselt(
    make_session, sitzungsbank, tmp_path
):
    _konto(make_session, provider="sitzungsbank", pin="0815-geheim")
    _abruf(make_session)
    zugang, konto = _zugang(make_session)
    assert zugang == {"pin": "0815-geheim", "sitzung": "geheime-sitzung+"}
    assert konto.zustand is KontoZustand.BEREIT
    _abruf(make_session)
    assert _zugang(make_session)[0]["sitzung"] == "geheime-sitzung++"
    roh = (tmp_path / "l.db").read_bytes()
    assert b"0815-geheim" not in roh and b"geheime-sitzung" not in roh


def test_zugang_auch_bei_noetiger_freigabe_gesichert(make_session, sitzungsbank):
    _konto(make_session, provider="sitzungsbank")
    Sitzungsbank.freigabe_noetig = True
    (ergebnis,) = _abruf(make_session)
    assert ergebnis.zustand is KontoZustand.FREIGABE_NOETIG
    zugang, konto = _zugang(make_session)
    assert zugang["sitzung"] == "geheime-sitzung+"
    assert konto.meldung == "Bitte freigeben"


def test_mit_freigabe_wird_je_konto_gesichert(make_session):
    """Schlussprüfung T-M2: ``fints freigeben`` fragt je Konto nach TAN bzw. App —
    was Konto 1 brachte, ist festgeschrieben, bevor Konto 2 auf den Menschen wartet;
    keine Transaktion (und keine Sperre) bleibt über die Rückfrage offen.

    Geprüft wird der Stand des Bankkontos 1 (letzter Abruf): Die Umsätze allein
    taugen unter SQLite nicht als Beleg — das RELEASE des äußersten SAVEPOINT
    (``begin_nested``) schreibt sie schon fest (Abschlussprüfung N-F)."""
    _konto(make_session, iban="DE01")
    _konto(make_session, iban="DE02")
    Attrappe.antworten["DE01"] = Abruf([umsatz()])
    Attrappe.antworten["DE02"] = Abruf([umsatz(betrag="-7")])
    gesehen: list[object] = []
    original = Attrappe.abrufen

    def abrufen(self, konto, zugang, ab):  # type: ignore[no-untyped-def]
        if konto.iban == "DE02":  # die Rückfrage: was sieht ein anderer Prozess?
            with make_session() as anderer:
                (de01,) = [k for k in lade_bankkonten(anderer) if k.iban == "DE01"]
                gesehen.append(de01.letzter_abruf)
        return original(self, konto, zugang, ab)

    Attrappe.abrufen = abrufen  # type: ignore[method-assign]
    try:
        with make_session() as s:
            rufe_ab(s, SCHLUESSEL, freigabe=lambda frage: "123456", sichern=s.commit)
            s.commit()
    finally:
        Attrappe.abrufen = original  # type: ignore[method-assign]
    assert len(gesehen) == 1 and gesehen[0] is not None


@pytest.mark.parametrize(
    "befehl",
    [["fints", "freigeben"], ["bank", "lauf", "--no-llm"]],
)
def test_cli_sichert_je_konto(tmp_path, monkeypatch, befehl):
    """N-F (F2): ``fints freigeben`` und ``bank lauf`` reichen ``sichern`` an den
    Abruf weiter — sonst bliebe die Transaktion über TAN-Abfrage bzw. Netzabruf
    offen, unter PostgreSQL mit der Schreibsperre."""
    from typer.testing import CliRunner

    from accounti.bank import lauf
    from accounti.cli import app

    monkeypatch.setenv("ACCOUNTI_KONFIG", str(tmp_path / "fehlt.yaml"))
    for name in ("ACCOUNTI_DB", "ACCOUNTI_GESELLSCHAFT"):
        monkeypatch.delenv(name, raising=False)
    url = f"sqlite:///{tmp_path / 'f.db'}"
    if befehl[0] == "fints":
        engine, fabrik = session_factory(url)
        init_db(engine)
        with fabrik() as s:
            speichere_bankkonto(
                s, Bankkonto(iban="DE01", bezeichnung="Giro", provider="fints")
            )
            s.commit()
        engine.dispose()
    aufrufe: list[dict[str, object]] = []

    def rufe_ab_attrappe(session, *args, **kw):  # type: ignore[no-untyped-def]
        aufrufe.append(kw)
        return []

    monkeypatch.setattr(lauf, "rufe_ab", rufe_ab_attrappe)
    r = CliRunner().invoke(app, [*befehl, "--db", url])
    assert r.exit_code == 0, r.output
    assert len(aufrufe) == 1 and callable(aufrufe[0].get("sichern"))
