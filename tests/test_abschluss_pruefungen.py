"""Abschlussprüfungen — je Prüfung ein auslösender und ein nicht auslösender Fall."""

from datetime import date
from decimal import Decimal

import pytest

from accounti.abschluss.kassenbuch import anfangsbestand, buche_kasse
from accounti.abschluss.pruefungen import (
    Schwere,
    blockiert,
    erfasse_kontoauszugssaldo,
    kontext,
    pruefe_abschluss,
)
from accounti.anlagen.lauf import afa_lauf, freigeben
from accounti.db.repository import speichere_bankkonto, speichere_transaktion
from accounti.models import Bankkonto, BuchungStatus, Transaktion, TransaktionQuelle
from accounti.models.anlagen import AfaArt
from tests.abschluss_hilfe import anlegen, buche, datenbank

D = Decimal
J = 2026


@pytest.fixture
def make_session(tmp_path):
    yield from datenbank(tmp_path)


@pytest.fixture
def config(tmp_path):
    return tmp_path / "accounti.yaml"  # fehlt: Standards (SKR03, EÜR)


def befunde(make_session, config, pruefung):
    with make_session() as s:
        return pruefe_abschluss(kontext(s, J, config), nur=[pruefung])


def bankkonto(make_session, iban="DE02120300000000202051", sachkonto="1200"):
    k = Bankkonto(iban=iban, bezeichnung=f"Giro {iban[-4:]}", sachkonto=sachkonto)
    with make_session() as s:
        speichere_bankkonto(s, k)
        s.commit()
    return k


def auszug(make_session, konto, saldo, stichtag=date(J, 12, 31)):
    with make_session() as s:
        erfasse_kontoauszugssaldo(s, konto.iban, stichtag, D(saldo), "test")
        s.commit()


def eb(make_session, konto, betrag):
    """Eröffnungsbilanz: Konto gegen Kapital, über 9000."""
    buche(make_session, date(J, 1, 1), konto, "9000", betrag, "EB", beleg_nummer="EB")
    buche(make_session, date(J, 1, 1), "9000", "0880", betrag, "EB", beleg_nummer="EB")


# --- Akzeptanz 5: Bank-Saldenabstimmung -------------------------------------------


def test_akzeptanz_5_abweichung_zum_kontoauszug_blockiert(make_session, config):
    k = bankkonto(make_session)
    eb(make_session, "1200", "5000")
    buche(
        make_session,
        date(J, 6, 1),
        "4930",
        "1200",
        "100",
        steuer_schluessel=9,
        steuer_betrag=D("19"),
    )
    auszug(make_session, k, "4900.00")  # Buchbestand: 4.881,00
    b = befunde(make_session, config, "bank")
    assert [x.schwere for x in b] == [Schwere.FEHLER]
    assert "4.881,00" in b[0].text and "4.900,00" in b[0].text and "19,00" in b[0].text
    assert blockiert(b)


def test_bank_stimmt(make_session, config):
    k = bankkonto(make_session)
    eb(make_session, "1200", "5000")
    buche(
        make_session,
        date(J, 6, 1),
        "4930",
        "1200",
        "100",
        steuer_schluessel=9,
        steuer_betrag=D("19"),
    )
    auszug(make_session, k, "4881")
    assert befunde(make_session, config, "bank") == []


def test_bank_zwei_konten_auf_einem_sachkonto(make_session, config):
    a = bankkonto(make_session, "DE02120300000000202051")
    b = bankkonto(make_session, "DE02500105170137075030")
    eb(make_session, "1200", "300")
    auszug(make_session, a, "100")
    assert "fehlt" in befunde(make_session, config, "bank")[0].text
    auszug(make_session, b, "200")
    assert befunde(make_session, config, "bank") == []


def test_bank_nicht_eingerichtet(make_session, config):
    eb(make_session, "1200", "300")
    (b,) = befunde(make_session, config, "bank")
    assert b.schwere is Schwere.FEHLER and "nicht eingerichtet" in b.text


def test_weiteres_bank_sachkonto_ohne_einrichtung_blockiert(make_session, config):
    """Jedes Bankkonto des Kontenrahmens mit Bestand/Verkehr wird abgestimmt."""
    k = bankkonto(make_session)
    eb(make_session, "1200", "1000")
    auszug(make_session, k, "1000")
    eb(make_session, "1210", "5000")
    buche(make_session, date(J, 3, 1), "4930", "1210", "100")
    buche(make_session, date(J, 4, 1), "1210", "8400", "300")
    buche(make_session, date(J, 5, 1), "1360", "1210", "200")
    (b,) = befunde(make_session, config, "bank")
    assert b.schwere is Schwere.FEHLER
    assert "1210" in b.text and "nicht eingerichtet" in b.text
    assert "--sachkonto 1210" in b.text
    # Kasse, Geldtransit und Finanzmittelanlagen sind keine Bankkonten
    buche(make_session, date(J, 6, 1), "1000", "1290", "50")
    assert ["1210" in x.text for x in befunde(make_session, config, "bank")] == [True]
    # eingerichtet und abgestimmt: kein Befund mehr
    zweites = bankkonto(make_session, "DE02500105170137075030", sachkonto="1210")
    auszug(make_session, zweites, "5000")
    assert befunde(make_session, config, "bank") == []


def test_bankkonten_skr04(make_session, tmp_path):
    datei = tmp_path / "skr04.yaml"
    datei.write_text("buchhaltung:\n  kontenrahmen: SKR04\n", encoding="utf-8")
    buche(make_session, date(J, 3, 1), "1810", "4400", "100")
    buche(make_session, date(J, 3, 2), "1600", "4400", "100")  # Kasse
    (b,) = befunde(make_session, datei, "bank")
    assert "1810" in b.text and "nicht eingerichtet" in b.text


# --- übrige Prüfungen -------------------------------------------------------------


def test_unfreigegebene_buchungen(make_session, config):
    buche(make_session, date(J, 3, 1), "4930", "1200", "10")
    buche(
        make_session,
        date(J - 1, 3, 1),
        "4930",
        "1200",
        "10",
        status=BuchungStatus.ZUR_PRUEFUNG,
    )
    assert befunde(make_session, config, "unfreigegeben") == []
    buche(
        make_session,
        date(J, 3, 2),
        "4930",
        "1200",
        "10",
        status=BuchungStatus.ZUR_PRUEFUNG,
    )
    (b,) = befunde(make_session, config, "unfreigegeben")
    assert b.schwere is Schwere.FEHLER and "1 Buchung" in b.text


def test_ungebuchte_umsaetze(make_session, config):
    tx = Transaktion(
        datum=date(J, 5, 1),
        betrag=D("-10"),
        verwendungszweck="Gebühr",
        quelle=TransaktionQuelle.BANK,
        rohtext="x",
    )
    with make_session() as s:
        speichere_transaktion(s, tx)
        s.commit()
    (b,) = befunde(make_session, config, "ungebucht")
    assert b.schwere is Schwere.FEHLER
    buche(make_session, date(J, 5, 1), "4970", "1200", "10", transaktion_id=tx.id)
    assert befunde(make_session, config, "ungebucht") == []


def test_kassenbuch_gegen_kassenkonto(make_session, config):
    from accounti.abschluss.konfiguration import KassenEinstellungen

    kasse = KassenEinstellungen(konto="1000")
    with make_session() as s:
        anfangsbestand(s, D("100"), date(J, 1, 1), kasse)
        buche_kasse(s, D("-24.90"), "Porto", kasse, date(J, 3, 1), gegenkonto="4910")
        s.commit()
    (b,) = befunde(make_session, config, "kasse")  # EB der Kasse fehlt
    assert b.schwere is Schwere.FEHLER and "75,10" in b.text
    eb(make_session, "1000", "100")
    assert befunde(make_session, config, "kasse") == []


def test_anlagen_afa_und_anlagekonto(make_session, config, tmp_path):
    from accounti.anlagen.konfiguration import lade_anlagen

    anlegen(make_session, 1300, date(J, 1, 1), nd=13, konto="0420")
    buche(make_session, date(J, 1, 1), "0420", "1200", "1300")
    texte = " ".join(b.text for b in befunde(make_session, config, "anlagen"))
    assert "AfA" in texte and "100,00" in texte
    with make_session() as s:
        afa_lauf(s, J, lade_anlagen(config))
        freigeben(s, J, "test")
        s.commit()
    assert befunde(make_session, config, "anlagen") == []
    # Anlagekonto ohne Anlagegut
    buche(make_session, date(J, 2, 1), "0420", "1200", "500")
    (b,) = befunde(make_session, config, "anlagen")
    assert "0420" in b.text and "1.700,00" in b.text and "1.200,00" in b.text


def test_verrechnungskonten(make_session, config):
    assert befunde(make_session, config, "verrechnungskonten") == []
    buche(make_session, date(J, 12, 30), "1360", "1200", "50")
    (b,) = befunde(make_session, config, "verrechnungskonten")
    assert b.schwere is Schwere.WARNUNG and "1360" in b.text


def test_vortragskonten_ausgeglichen(make_session, config):
    eb(make_session, "1200", "100")
    assert befunde(make_session, config, "vortragskonten") == []
    buche(make_session, date(J, 1, 1), "1000", "9000", "50", "EB", beleg_nummer="EB")
    (b,) = befunde(make_session, config, "vortragskonten")
    assert b.schwere is Schwere.FEHLER and "50,00" in b.text


def test_euer_offene_personenkonten_und_zuordnung(make_session, config, tmp_path):
    buche(make_session, date(J, 3, 1), "4930", "70001", "100")
    buche(make_session, date(J, 3, 1), "2200", "1200", "10")  # bewusst außerhalb
    buche(make_session, date(J, 3, 1), "5900", "1200", "10")  # ohne Zuordnung
    (p,) = befunde(make_session, config, "euer_personenkonten")
    assert p.schwere is Schwere.WARNUNG and "70001" in p.text
    (z,) = befunde(make_session, config, "euer_zuordnung")
    assert z.schwere is Schwere.WARNUNG and "5900" in z.text and "2200" not in z.text
    bilanz = tmp_path / "bilanz.yaml"
    bilanz.write_text("abschluss:\n  gewinnermittlung: bilanz\n", encoding="utf-8")
    assert befunde(make_session, bilanz, "euer_personenkonten") == []


def test_euer_zuordnung_mit_hinweis_je_konto(make_session, config):
    """Konten mit hinterlegtem Hinweis: ohne Zeile eine Warnung mit dem Grund, mit
    Zeile oder außerhalb der EÜR ein Hinweis; die übrigen bleiben allgemein."""
    buche(make_session, date(J, 3, 1), "4870", "0525", "200")  # Teilwert: ohne Zeile
    buche(make_session, date(J, 3, 1), "5900", "1200", "10")  # ohne Zeile, ohne Hinweis
    buche(make_session, date(J, 3, 1), "2504", "1200", "5")  # Umwandlung: „-“
    funde = befunde(make_session, config, "euer_zuordnung")
    texte = {b.text: b.schwere for b in funde}
    assert len(funde) == 3
    [teilwert] = [t for t in texte if "4870" in t]
    assert texte[teilwert] is Schwere.WARNUNG
    assert "Teilwertabschreibung in der EÜR nicht zulässig – Buchung stornieren" in (
        teilwert
    )
    assert "5900" not in teilwert
    [allgemein] = [t for t in texte if "5900" in t]
    assert texte[allgemein] is Schwere.WARNUNG and "kontenzuordnung" in allgemein
    [umwandlung] = [t for t in texte if "2504" in t]
    assert texte[umwandlung] is Schwere.HINWEIS
    assert umwandlung.startswith("Konto 2504: Umwandlungsergebnis")


def test_alle_pruefungen_und_unbekannte(make_session, config):
    with make_session() as s:
        alle = pruefe_abschluss(kontext(s, J, config))
        assert alle == [] or not blockiert(alle)
        with pytest.raises(ValueError, match="unbekannt"):
            pruefe_abschluss(kontext(s, J, config), nur=["gibtsnicht"])


def test_gwg_anlage_ohne_afa_konto_eintrag(make_session, config):
    """Eine GWG auf 0480 mit gebuchter Sofortabschreibung ist in Ordnung."""
    from accounti.anlagen.konfiguration import lade_anlagen

    anlegen(make_session, 700, date(J, 3, 1), AfaArt.GWG)
    buche(make_session, date(J, 3, 1), "0480", "1200", "700")
    with make_session() as s:
        afa_lauf(s, J, lade_anlagen(config))
        freigeben(s, J, "test")
        s.commit()
    assert befunde(make_session, config, "anlagen") == []


def test_abgrenzungen_entschieden(make_session, tmp_path):
    """Ein offener ARAP-/PRAP-Vorschlag ist eine offene Bewertung — Fehler."""
    from accounti.abschluss.abgrenzung import (
        lehne_abgrenzung_ab,
        schlage_abgrenzungen_vor,
    )
    from accounti.abschluss.konfiguration import lade_abschluss
    from accounti.anlagen.rechtsstand import lade_rechtsstand

    bilanz = tmp_path / "bilanz.yaml"
    bilanz.write_text("abschluss:\n  gewinnermittlung: bilanz\n", encoding="utf-8")
    assert befunde(make_session, bilanz, "abgrenzungen") == []
    buche(
        make_session,
        date(J, 12, 1),
        "4360",
        "1200",
        "1200",
        "Versicherung 01.01.2027-31.12.2027",
    )
    with make_session() as s:
        (v,) = schlage_abgrenzungen_vor(
            s, J, lade_abschluss(bilanz), lade_rechtsstand()
        ).vorschlaege
        s.commit()
    (b,) = befunde(make_session, bilanz, "abgrenzungen")
    assert b.schwere is Schwere.FEHLER and "1 Abgrenzungsvorschlag" in b.text
    with make_session() as s:
        lehne_abgrenzung_ab(s, str(v.nr), "test")
        s.commit()
    assert befunde(make_session, bilanz, "abgrenzungen") == []


def test_gebaeudekonto_ohne_anlagegut_und_ausnahme_per_konfiguration(
    make_session, config, tmp_path
):
    """Gebäude-AfA (§ 7 Abs. 4) fehlt: ein Gebäudekonto sperrt, bis es aus
    ``anlagen.anlagekonten`` genommen wird (Grenze im Plan)."""
    buche(make_session, date(J, 2, 1), "0080", "1200", "300000")  # Bauten
    buche(make_session, date(J, 12, 31), "4831", "0080", "9000")  # 3 % AfA
    (b,) = befunde(make_session, config, "anlagen")
    assert b.schwere is Schwere.FEHLER and "0080" in b.text
    ohne_bauten = tmp_path / "ohne_bauten.yaml"
    ohne_bauten.write_text(
        "anlagen:\n  anlagekonten: [['0010', '0049'], ['0200', '0499']]\n",
        encoding="utf-8",
    )
    assert befunde(make_session, ohne_bauten, "anlagen") == []
