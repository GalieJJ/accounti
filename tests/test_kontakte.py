from datetime import date

import pytest

from accounti.konfiguration import Buchhaltung, lade_buchhaltung
from accounti.kontakte.erkennung import (
    finde_kontakt,
    naechste_kontonummer,
    normalisiere_name,
)
from accounti.models import Kontakt


@pytest.mark.parametrize(
    "name",
    [
        "Bürobedarf Müller GmbH",
        "BUEROBEDARF MÜLLER G.m.b.H.",
        "Buerobedarf Mueller",
        "  bürobedarf   müller gmbh & co. kg ",
    ],
)
def test_namensvarianten_werden_gleich(name):
    assert normalisiere_name(name) == "buerobedarf mueller"


def test_unterschiedliche_firmen_bleiben_verschieden():
    assert normalisiere_name("Müller Bürobedarf GmbH") != normalisiere_name(
        "Bürobedarf Müller GmbH"
    )


KONTAKTE = [
    Kontakt(
        name="Bürobedarf Müller GmbH",
        kreditor_konto="70001",
        iban="DE89370400440532013000",
    ),
    Kontakt(
        name="Druckerei Beispiel GmbH", kreditor_konto="70002", ust_id="DE111111111"
    ),
    Kontakt(name="Atelier Kundin GmbH", debitor_konto="10001"),
]


def test_erkennung_reihenfolge_iban_ustid_name():
    k, merkmal = finde_kontakt(KONTAKTE, iban="DE89 3704 0044 0532 0130 00")
    assert (k.name, merkmal) == ("Bürobedarf Müller GmbH", "IBAN")
    k, merkmal = finde_kontakt(KONTAKTE, ust_id="de 111 111 111", name="Irgendwas")
    assert (k.name, merkmal) == ("Druckerei Beispiel GmbH", "USt-IdNr.")
    k, merkmal = finde_kontakt(KONTAKTE, name="ATELIER KUNDIN")
    assert (k.name, merkmal) == ("Atelier Kundin GmbH", "Name")


def test_iban_schlaegt_namen():
    k, _ = finde_kontakt(
        KONTAKTE, iban="DE89370400440532013000", name="Druckerei Beispiel GmbH"
    )
    assert k.name == "Bürobedarf Müller GmbH"


def test_kein_treffer():
    assert finde_kontakt(KONTAKTE, name="Unbekannt AG") == (None, None)
    assert finde_kontakt(KONTAKTE) == (None, None)


def test_naechste_kontonummer():
    assert naechste_kontonummer(set(), 70000, 99999) == "70000"
    assert naechste_kontonummer({"70000", "70001", "70003"}, 70000, 99999) == "70004"
    assert naechste_kontonummer({"10000", "70005"}, 70000, 99999) == "70006"


def test_kreis_voll():
    with pytest.raises(ValueError, match="voll"):
        naechste_kontonummer({"70000", "70001"}, 70000, 70001)


def test_buchhaltung_standard_ohne_datei(tmp_path):
    b = lade_buchhaltung(tmp_path / "fehlt.yaml")
    assert (b.debitoren_von, b.debitoren_bis) == (10000, 69999)
    assert (b.kreditoren_von, b.kreditoren_bis) == (70000, 99999)
    assert b.bank_konto == "1200"
    assert b.standard_zahlungsziel_tage == 14


def test_buchhaltung_aus_datei(tmp_path):
    pfad = tmp_path / "accounti.yaml"
    pfad.write_text(
        "buchhaltung:\n  kreditoren_von: 71000\n  standard_aufwand: '4980'\n",
        encoding="utf-8",
    )
    b = lade_buchhaltung(pfad)
    assert b.kreditoren_von == 71000
    assert b.standard_aufwand == "4980"
    assert isinstance(b, Buchhaltung)


def test_kontakt_rollen():
    k = Kontakt(name="X", kreditor_konto="70001", debitor_konto="10001")
    assert k.ist_kreditor and k.ist_debitor
    assert k.erstellt_am.date() <= date.today()


# --- Gesamttest Paket C: Treffer, die dem Beleg widersprechen (B14, Ausgang B1) ---


def test_gleiche_iban_andere_ustid_ist_ein_anderes_unternehmen():
    """B14: Factoring-IBAN — Rechnung einer anderen Firma (andere USt-IdNr.)."""
    from accounti.kontakte.erkennung import suche_kontakt

    mueller = Kontakt(
        name="Bürobedarf Müller GmbH",
        kreditor_konto="70000",
        iban="DE89370400440532013000",
        ust_id="DE123456789",
    )
    r = suche_kontakt(
        [mueller],
        iban="DE89 3704 0044 0532 0130 00",
        ust_id="DE222222222",
        name="Papierhaus Kiel GmbH",
    )
    assert r.kontakt is None and "Factoring" in r.widerspruch
    # gleiche IBAN, anderer Name, keine USt-IdNr. zum Vergleich: Treffer zur Prüfung
    r = suche_kontakt(
        [mueller], iban="DE89370400440532013000", name="Papierhaus Kiel GmbH"
    )
    assert r.kontakt is mueller and "Papierhaus Kiel" in r.widerspruch
    # gleiche IBAN und USt-IdNr., anderer Name: derselbe (umfirmiert)
    r = suche_kontakt(
        [mueller], iban="DE89370400440532013000", ust_id="DE123456789", name="Neu AG"
    )
    assert (r.kontakt, r.widerspruch) == (mueller, None)


def test_namenstreffer_mit_anderer_ustid_oder_anderem_land_zaehlt_nicht():
    """Ausgang B1: „Atelier Nord SARL“ (FR) und „Atelier Nord SRL“ (IT)."""
    from accounti.kontakte.erkennung import suche_kontakt

    nord_fr = Kontakt(
        name="Atelier Nord SARL",
        land="FR",
        ust_id="FR40303265045",
        debitor_konto="10000",
        plz="75001",
    )
    r = suche_kontakt(
        [nord_fr], ust_id="IT00743110157", name="Atelier Nord SRL", land="IT"
    )
    assert r.kontakt is None and "10000" in r.widerspruch
    rossi = Kontakt(name="Anna Rossi", land="AT", debitor_konto="10001")
    assert suche_kontakt([rossi], name="Anna Rossi", land="IT").kontakt is None
    assert suche_kontakt([rossi], name="Anna Rossi", land="AT").kontakt is rossi


def test_kunde_aus_eigener_rechnung_nur_mit_gleicher_plz_oder_email():
    from accounti.kontakte.erkennung import suche_kontakt

    muenchen = Kontakt(
        name="Max Müller",
        plz="81541",
        email="max.muenchen@example.org",
        debitor_konto="10000",
    )
    berlin = suche_kontakt(
        [muenchen],
        name="Max Müller",
        plz="10117",
        email="mueller.berlin@example.net",
        mit_anschrift=True,
    )
    assert berlin.kontakt is None and "PLZ" in berlin.widerspruch
    umgezogen = suche_kontakt(
        [muenchen],
        name="Max Müller",
        plz="10117",
        email="MAX.MUENCHEN@example.org",
        mit_anschrift=True,
    )
    assert umgezogen.kontakt is muenchen
