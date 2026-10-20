"""Plausibilisierung vor der Abgabe: je Regel ein auslösender und ein ruhiger Fall."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

import pytest

from accounti.models import Buchungssatz, BuchungStatus, Kontakt
from accounti.steuer.kennziffern import Kontenplan, ermittle
from accounti.steuer.plausibilitaet import (
    Befund,
    Schwellen,
    Schweregrad,
    freigabe_gesperrt,
    plausibilisiere,
)
from accounti.steuer.voranmeldung import UStVoranmeldung
from accounti.steuer.zeitraum import Zeitraum

D = Decimal

AUGUST = Zeitraum.lies("2026-08")
TAG = date(2026, 8, 14)
WIEN = Kontakt(
    name="Rahmen Wien", land="AT", ust_id="ATU12345678", debitor_konto="10002"
)
PARIS_PRIVAT = Kontakt(name="Mme Dupont", land="FR", debitor_konto="10003")
KONTAKTE = [WIEN, PARIS_PRIVAT]


@dataclass
class Lage:
    bestaetigt: bool
    grund: str


def bestaetigt(ust_id, stichtag):
    return Lage(True, "gültig, qualifiziert bestätigt")


def unbestaetigt(ust_id, stichtag):
    return Lage(False, "keine Bestätigung seit 15.07.2026")


def b(soll, haben, netto, schluessel=None, steuer=None, **kw):
    return Buchungssatz(
        datum=kw.pop("datum", TAG),
        soll_konto=soll,
        haben_konto=haben,
        betrag_netto=D(netto),
        steuer_schluessel=schluessel,
        steuer_betrag=D(steuer) if steuer is not None else None,
        buchungstext="Test",
        status=kw.pop("status", BuchungStatus.AUTO_GEBUCHT),
        **kw,
    )


def pruefe(buchungen, bestaetigung=bestaetigt, **kw):
    e = ermittle(buchungen, AUGUST, Kontenplan(), KONTAKTE)
    return plausibilisiere(e, bestaetigung=bestaetigung, kontakte=KONTAKTE, **kw)


def regeln(befunde, schweregrad=None):
    return [
        x.regel for x in befunde if schweregrad is None or x.schweregrad is schweregrad
    ]


def test_ruhiger_monat_hat_keine_fehler():
    befunde = pruefe([b("10001", "8400", "1000", 3, "190")], weitere=[])
    assert regeln(befunde) == []
    assert not freigabe_gesperrt(befunde)


def test_ohne_baustein_7_ein_hinweis():
    befunde = pruefe([b("10001", "8400", "1000", 3, "190")])
    assert regeln(befunde) == ["periode"]
    assert befunde[0].schweregrad is Schweregrad.HINWEIS
    assert not freigabe_gesperrt(befunde)


def test_buchung_ohne_steuerschluessel_sperrt():
    befunde = pruefe([b("10001", "8200", "100")], weitere=[])
    assert regeln(befunde, Schweregrad.FEHLER) == ["ohne_steuerschluessel"]
    assert "8200" in befunde[0].text
    assert freigabe_gesperrt(befunde)


def test_offene_buchung_sperrt():
    befunde = pruefe(
        [b("10001", "8400", "100", 3, "19", status=BuchungStatus.ZUR_PRUEFUNG)],
        weitere=[],
    )
    assert regeln(befunde, Schweregrad.FEHLER) == ["offene_buchungen"]


@pytest.mark.parametrize("konto", ["8125", "8336"])
def test_ig_umsatz_ohne_bestaetigte_ustid_sperrt(konto):
    befunde = pruefe([b("10002", konto, "500")], bestaetigung=unbestaetigt, weitere=[])
    assert regeln(befunde, Schweregrad.FEHLER) == ["ustid"]
    assert "ATU12345678" in befunde[0].text
    assert "pruefe-ustid 10002" in befunde[0].text
    assert regeln(pruefe([b("10002", konto, "500")], weitere=[])) == []


def test_ig_lieferung_an_unbekannten_abnehmer_sperrt():
    befunde = pruefe([b("1200", "8125", "500")], weitere=[])
    assert regeln(befunde, Schweregrad.FEHLER) == ["ustid"]
    assert "Abnehmer unbekannt" in befunde[0].text


def test_minderung_braucht_keine_bestaetigung():
    befunde = pruefe([b("8125", "10002", "20")], bestaetigung=unbestaetigt, weitere=[])
    assert regeln(befunde) == []


def test_verprobung_gebuchte_gegen_gemeldete_umsatzsteuer():
    # gebucht 200 € statt 19 % von 1.000 €
    befunde = pruefe([b("10001", "8400", "1000", 3, "200")], weitere=[])
    assert regeln(befunde, Schweregrad.WARNUNG) == ["verprobung"]
    assert (
        regeln(pruefe([b("10001", "8400", "1000.99", 3, "190.19")], weitere=[])) == []
    )


def test_kennziffern_intern_konsistent():
    e = ermittle([], AUGUST, Kontenplan())
    e.voranmeldung.addiere(46, D("1000"))  # Bemessungsgrundlage ohne Steuer
    e.voranmeldung.addiere(84, D("100"))
    e.voranmeldung.addiere(85, D("50"))  # 50 % passen zu keinem Steuersatz
    befunde = plausibilisiere(e, bestaetigung=bestaetigt, weitere=[])
    assert sorted(regeln(befunde)) == ["konsistenz", "konsistenz"]
    assert {x.schweregrad for x in befunde} == {Schweregrad.FEHLER, Schweregrad.WARNUNG}


def _va(kz83_aus_81: str) -> UStVoranmeldung:
    va = UStVoranmeldung(zeitraum="x")
    va.addiere(81, D(kz83_aus_81))
    return va


def test_vergleich_mit_vormonat_und_vorjahresmonat():
    buchungen = [b("10001", "8400", "100000", 3, "19000")]  # Kz 83: 19.000 €
    befunde = pruefe(
        buchungen, vorperiode=_va("10000"), vorjahr=_va("100000"), weitere=[]
    )
    assert regeln(befunde) == ["vergleich"]
    assert befunde[0].schweregrad is Schweregrad.HINWEIS
    assert "Vormonat" in befunde[0].text
    # kleine absolute Abweichung: kein Hinweis, auch wenn prozentual groß
    klein = pruefe(
        [b("10001", "8400", "1000", 3, "190")],
        vorperiode=_va("100"),
        schwellen=Schwellen(abweichung_mindestens=D("1000")),
        weitere=[],
    )
    assert regeln(klein) == []


def test_eu_privatkunde_mit_deutscher_ust_bei_oss():
    buchungen = [b("10003", "8400", "200", 3, "38")]
    befunde = pruefe(buchungen, oss_aktiv=True, weitere=[])
    assert regeln(befunde, Schweregrad.WARNUNG) == ["oss"]
    assert "Mme Dupont" in befunde[0].text
    assert regeln(pruefe(buchungen, oss_aktiv=False, weitere=[])) == []


def test_weitere_befunde_aus_anderen_bausteinen():
    extern = Befund("periode_abgeschlossen", Schweregrad.FEHLER, "August ist offen")
    befunde = pruefe([], weitere=[extern])
    assert befunde == [extern]
    assert freigabe_gesperrt(befunde)
