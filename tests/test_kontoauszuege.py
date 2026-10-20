"""Kontoauszüge: lückenlos nummeriert, schlüssiger Saldenverlauf (Akzeptanz 6).

Die Empfänger-Simulation liest das MT940 so, wie ein Kanzleiprogramm es tut: je
Nachricht Auszugsnummer (``:28C:``), Anfangssaldo (``:60F:``), Umsätze (``:61:``) und
Schlusssaldo (``:62F:``) — und prüft, dass die Kette ohne Lücke und Sprung aufgeht.
"""

import re
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

import pytest
from sqlalchemy import update

from accounti.db import init_db, session_factory
from accounti.db.repo_export import (
    lade_kontoauszuege,
    speichere_kontoauszug,
    zugeordnete_transaktion_ids,
)
from accounti.db.repository import speichere_bankkonto, speichere_transaktion
from accounti.db.tabellen import TransaktionRow
from accounti.db.tabellen_export import KontoauszugRow, KontoauszugUmsatzRow
from accounti.export.kontoauszuege import (
    KontoauszugError,
    erstelle_auszuege,
    kontobezeichnung,
    lade_umsaetze,
    mt940,
    pruefe_auszuege,
    saldenverlauf_csv,
    swift_text,
)
from accounti.models import Bankkonto, Transaktion, TransaktionQuelle
from accounti.models.export import Kontoauszug

D = Decimal
HEUTE = date(2027, 2, 10)


@pytest.fixture
def s(tmp_path):
    engine, make = session_factory(f"sqlite:///{tmp_path / 'k.db'}")
    init_db(engine)
    with make() as session:
        yield session


def _tx(s, datum, betrag, konto="1200", zweck="Umsatz", **kw):
    tx = Transaktion(
        datum=datum,
        betrag=D(betrag),
        verwendungszweck=zweck,
        quelle=kw.pop("quelle", TransaktionQuelle.BANK),
        rohtext="",
        sachkonto=konto,
        **kw,
    )
    speichere_transaktion(s, tx)
    s.flush()
    return tx


def _erstelle(s, bis, **kw):
    kw.setdefault("heute", HEUTE)
    return erstelle_auszuege(s, "1200", bis, **kw)


# ---------------------------------------------------------------------------
# Empfänger-Simulation
# ---------------------------------------------------------------------------


def _betrag(text):
    return D(text.replace(",", "."))


def lies_mt940(inhalt):
    """Nachrichten mit Nummer, Salden und Umsätzen — wie ein Kanzleiprogramm."""
    text = inhalt.decode("ascii")
    nachrichten = []
    for teil in text.split("\r\n-"):
        if not teil.strip():
            continue
        assert teil.startswith("\r\n:20:"), teil[:30]
        felder = re.findall(r"\r\n:(\w+):(.*?)(?=\r\n:|\Z)", teil, re.S)
        werte = {}
        umsaetze = []
        for tag, wert in felder:
            if tag == "61":
                m = re.fullmatch(
                    r"(\d{6})(\d{4})(C|D)(\d+,\d{2})N(\w{3})(.{1,16})", wert
                )
                assert m, wert
                umsaetze.append((m[1], (1 if m[3] == "C" else -1) * _betrag(m[4])))
            else:
                werte.setdefault(tag, []).append(wert)
        saldo = {}
        for tag in ("60F", "62F"):
            m = re.fullmatch(r"([CD])(\d{6})EUR(\d+,\d{2})", werte[tag][0])
            assert m, werte[tag]
            saldo[tag] = (m[2], (1 if m[1] == "C" else -1) * _betrag(m[3]))
        nummer, blatt = werte["28C"][0].split("/")
        nachrichten.append(
            {
                "referenz": werte["20"][0],
                "konto": werte["25"][0],
                "nummer": int(nummer),
                "blatt": int(blatt),
                "anfang": saldo["60F"],
                "ende": saldo["62F"],
                "umsaetze": umsaetze,
                "86": werte.get("86", []),
            }
        )
    return nachrichten


# ---------------------------------------------------------------------------
# Repository
# ---------------------------------------------------------------------------


def test_repository(s):
    a = Kontoauszug(
        finanzkonto="1200",
        jahr=2026,
        nummer=1,
        von=date(2026, 7, 1),
        bis=date(2026, 7, 31),
        anfangssaldo=D("10.00"),
        endsaldo=D("15.50"),
        umsaetze=[UUID(int=2), UUID(int=1)],
        nachtraege=[UUID(int=1)],
        hash="h",
    )
    speichere_kontoauszug(s, a)
    (geladen,) = lade_kontoauszuege(s, "1200")
    assert geladen == a
    assert lade_kontoauszuege(s, "1210") == []
    assert zugeordnete_transaktion_ids(s) == {UUID(int=1), UUID(int=2)}


# ---------------------------------------------------------------------------
# Akzeptanz 6
# ---------------------------------------------------------------------------


def test_akzeptanz_6_lueckenlos_nummeriert_und_saldenverlauf_schluessig(s):
    _tx(s, date(2026, 6, 28), "999.99")  # vor dem ersten Auszug: im Anfangssaldo
    _tx(s, date(2026, 7, 3), "1190.00", zweck="Rechnung 2026-0815")
    _tx(s, date(2026, 7, 15), "-59.50", zweck="Tankstelle")
    _tx(s, date(2026, 7, 2), "300.00", konto="1210")  # anderes Finanzkonto

    erster = _erstelle(s, date(2026, 7, 31), anfangssaldo=D("1000.00"))
    assert [(a.nummer, a.endsaldo) for a in erster.neu] == [(1, D("2130.50"))]
    assert [b.code for b in erster.befunde] == ["vor_beginn"]

    nachtrag = _tx(s, date(2026, 7, 20), "-10.00", zweck="nachträglich importiert")
    _tx(s, date(2026, 8, 5), "250.00")
    _tx(s, date(2026, 10, 1), "-30.00")
    _tx(s, date(2026, 12, 31), "5.00")
    _tx(s, date(2027, 1, 4), "-100.00")
    _tx(s, date(2027, 2, 1), "1.00")  # Februar ist noch nicht dran

    zweiter = _erstelle(s, date(2027, 1, 31))
    assert [(a.jahr, a.nummer) for a in zweiter.neu] == [
        (2026, 2),  # August, mit Nachtrag aus Juli
        (2026, 3),  # September ohne Umsatz — trotzdem ein Auszug
        (2026, 4),
        (2026, 5),
        (2026, 6),
        (2027, 1),  # neues Jahr, neue Zählung
    ]
    assert [b.code for b in zweiter.befunde] == ["nachtrag"]
    august = zweiter.neu[0]
    assert august.nachtraege == [nachtrag.id] and len(august.umsaetze) == 2

    auszuege = lade_kontoauszuege(s, "1200")
    assert len(auszuege) == 7
    for vorher, nachher in zip(auszuege, auszuege[1:], strict=False):
        assert nachher.von == date.fromordinal(vorher.bis.toordinal() + 1)
        assert nachher.anfangssaldo == vorher.endsaldo
        assert nachher.nummer == (
            vorher.nummer + 1 if nachher.jahr == vorher.jahr else 1
        )
    assert auszuege[-1].endsaldo == D("2130.50") - 10 + 250 - 30 + 5 - 100
    assert pruefe_auszuege(s) == []

    # Empfänger: MT940 lesen und die Kette nachrechnen
    umsaetze = lade_umsaetze(s, auszuege)
    nachrichten = lies_mt940(mt940(auszuege, umsaetze, "37040044/532013000"))
    assert [n["nummer"] for n in nachrichten] == [1, 2, 3, 4, 5, 6, 1]
    assert nachrichten[0]["anfang"] == ("260630", D("1000.00"))
    for vorher, n in zip([None, *nachrichten], nachrichten, strict=False):
        assert n["blatt"] == 1 and n["konto"] == "37040044/532013000"
        assert n["anfang"][1] + sum(b for _, b in n["umsaetze"]) == n["ende"][1]
        if vorher:
            assert n["anfang"] == vorher["ende"]
    assert nachrichten[2]["umsaetze"] == []  # September
    assert ("260720", D("-10.00")) in nachrichten[1]["umsaetze"]

    # Saldenverlauf als Tabelle
    zeilen = saldenverlauf_csv(auszuege, umsaetze).decode("cp1252").split("\r\n")
    assert zeilen[0].startswith("Finanzkonto;Jahr;Auszug;Von;Bis;Anfangssaldo")
    assert zeilen[2].split(";")[:10] == [
        "1200",
        "2026",
        "2",
        "01.08.2026",
        "31.08.2026",
        "2130,50",
        "250,00",
        "-10,00",
        "2370,50",
        "2",
    ]


def test_erster_lauf_ab_einem_frueheren_monat(s):
    _tx(s, date(2026, 1, 5), "10.00")
    _tx(s, date(2026, 3, 5), "-4.00")
    lauf = _erstelle(s, date(2026, 3, 31), anfangssaldo=D("1"), ab=date(2026, 1, 1))
    assert [(a.nummer, a.endsaldo) for a in lauf.neu] == [
        (1, D("11.00")),
        (2, D("11.00")),
        (3, D("7.00")),
    ]
    with pytest.raises(KontoauszugError, match="--ab nur beim ersten"):
        _erstelle(s, date(2026, 4, 30), ab=date(2026, 4, 1))


def test_zweiter_lauf_schreibt_nichts_neu(s):
    _tx(s, date(2026, 7, 3), "10.00")
    _erstelle(s, date(2026, 7, 31), anfangssaldo=D("0"))
    lauf = _erstelle(s, date(2026, 7, 31))
    assert lauf.neu == [] and lauf.befunde == []
    assert len(lade_kontoauszuege(s)) == 1


def test_erster_auszug_braucht_anfangssaldo(s):
    with pytest.raises(KontoauszugError, match="--anfangssaldo"):
        _erstelle(s, date(2026, 7, 31))


def test_anfangssaldo_steht_nach_dem_ersten_auszug_fest(s):
    _erstelle(s, date(2026, 7, 31), anfangssaldo=D("5"))
    with pytest.raises(KontoauszugError, match="Endsaldo des Auszugs 1/2026"):
        _erstelle(s, date(2026, 8, 31), anfangssaldo=D("6"))
    assert _erstelle(s, date(2026, 8, 31), anfangssaldo=D("5.00")).neu


def test_laufender_monat_wird_nicht_festgeschrieben(s):
    with pytest.raises(KontoauszugError, match="noch nicht abgeschlossen"):
        _erstelle(s, date(2027, 2, 28), anfangssaldo=D("0"))
    with pytest.raises(KontoauszugError, match="Monatsende"):
        _erstelle(s, date(2026, 7, 15), anfangssaldo=D("0"))


def test_kontrollsaldo(s):
    _tx(s, date(2026, 7, 3), "10.00")
    with pytest.raises(KontoauszugError, match="Kontrollsaldo"):
        _erstelle(s, date(2026, 7, 31), anfangssaldo=D("0"), kontrollsaldo=D("11"))
    assert lade_kontoauszuege(s) == []  # nichts festgeschrieben
    lauf = _erstelle(s, date(2026, 7, 31), anfangssaldo=D("0"), kontrollsaldo=D("10"))
    assert lauf.neu[0].kontrollsaldo == D("10")


def test_kontrollsaldo_auch_fuer_festgeschriebenen_monat(s):
    """Ist der Monat schon festgeschrieben, prüft --kontrollsaldo den vorhandenen
    Auszug, statt still nichts zu tun."""
    _tx(s, date(2026, 7, 3), "10.00")
    _erstelle(s, date(2026, 8, 31), anfangssaldo=D("0"), ab=date(2026, 7, 1))
    with pytest.raises(KontoauszugError, match="Kontrollsaldo.*Auszugs 1/2026"):
        _erstelle(s, date(2026, 7, 31), kontrollsaldo=D("11"))
    assert _erstelle(s, date(2026, 7, 31), kontrollsaldo=D("10")).neu == []
    with pytest.raises(KontoauszugError, match="Kontrollsaldo.*Auszugs 2/2026"):
        _erstelle(s, date(2026, 8, 31), kontrollsaldo=D("0"))
    with pytest.raises(KontoauszugError, match="Kein festgeschriebener Auszug"):
        _erstelle(s, date(2026, 6, 30), kontrollsaldo=D("0"))


def test_fremdwaehrung_bleibt_draussen(s):
    _tx(s, date(2026, 7, 3), "10.00", waehrung="USD")
    lauf = _erstelle(s, date(2026, 7, 31), anfangssaldo=D("0"))
    assert lauf.neu[0].umsaetze == []
    assert [b.code for b in lauf.befunde] == ["fremdwaehrung"]


def test_standardkonto_fuer_umsaetze_ohne_sachkonto(s):
    _tx(s, date(2026, 7, 3), "10.00", konto=None)
    lauf = _erstelle(s, date(2026, 7, 31), anfangssaldo=D("0"))
    assert len(lauf.neu[0].umsaetze) == 1


# ---------------------------------------------------------------------------
# Prüfung findet Lücken, Sprünge und Änderungen
# ---------------------------------------------------------------------------


@pytest.fixture
def drei(s):
    _tx(s, date(2026, 7, 3), "10.00")
    tx = _tx(s, date(2026, 8, 3), "20.00")
    _tx(s, date(2026, 9, 3), "30.00")
    _erstelle(s, date(2026, 9, 30), anfangssaldo=D("100"), ab=date(2026, 7, 1))
    s.commit()
    return tx


def test_pruefung_findet_geaenderten_umsatz(s, drei):
    s.execute(
        update(TransaktionRow)
        .where(TransaktionRow.id == str(drei.id))
        .values(betrag=D("25.00"))
    )
    codes = {b.code for b in pruefe_auszuege(s)}
    assert {"summe", "hash"} <= codes


def test_pruefung_findet_fehlenden_auszug(s, drei):
    august = lade_kontoauszuege(s)[1]
    s.query(KontoauszugUmsatzRow).filter_by(auszug_id=str(august.id)).delete()
    s.query(KontoauszugRow).filter_by(id=str(august.id)).delete()
    befunde = pruefe_auszuege(s)
    codes = {b.code for b in befunde}
    assert {"luecke", "nummer", "saldensprung", "hash"} <= codes
    assert any("2026-08-01" in b.text for b in befunde if b.code == "luecke")


def test_pruefung_findet_geaenderten_saldo(s, drei):
    s.execute(
        update(KontoauszugRow)
        .where(KontoauszugRow.nummer == 3)
        .values(anfangssaldo=D("0"), endsaldo=D("30"))
    )
    codes = {b.code for b in pruefe_auszuege(s)}
    assert {"saldensprung", "hash"} <= codes


def test_pruefung_findet_verschobenes_datum(s, drei):
    s.execute(
        update(TransaktionRow)
        .where(TransaktionRow.id == str(drei.id))
        .values(datum=date(2026, 9, 2))
    )
    codes = {b.code for b in pruefe_auszuege(s)}
    assert {"zeitraum", "hash"} <= codes


@pytest.mark.parametrize(
    ("feld", "wert"),
    [
        ("verwendungszweck", "anderer Text"),
        ("gegenkonto_name", "Jemand Anderes"),
        ("gegenkonto_iban", "DE02120300000000202051"),
    ],
)
def test_pruefung_findet_geaenderten_text(s, drei, feld, wert):
    """Was ins Feld :86: geht, ist festgeschrieben wie Datum und Betrag."""
    s.execute(
        update(TransaktionRow)
        .where(TransaktionRow.id == str(drei.id))
        .values(**{feld: wert})
    )
    assert "hash" in {b.code for b in pruefe_auszuege(s)}


def test_pruefung_findet_geloeschten_umsatz(s, drei):
    s.query(TransaktionRow).filter_by(id=str(drei.id)).delete()
    assert "umsatz_fehlt" in {b.code for b in pruefe_auszuege(s)}


# ---------------------------------------------------------------------------
# MT940-Format
# ---------------------------------------------------------------------------


def test_mt940_aufbau(s):
    _tx(
        s,
        date(2026, 7, 3),
        "-1234.56",
        zweck="Miete Juli: Büro & Lager {Müller} " + "x" * 300,
        gegenkonto_name="Grundstücksgesellschaft Weiß",
        gegenkonto_iban="DE02120300000000202051",
    )
    _erstelle(s, date(2026, 7, 31), anfangssaldo=D("-50"))
    auszuege = lade_kontoauszuege(s)
    inhalt = mt940(auszuege, lade_umsaetze(s, auszuege), "DE89370400440532013000")
    assert inhalt.isascii()
    text = inhalt.decode("ascii")
    assert text.startswith("\r\n:20:1200-26-1\r\n:25:DE89370400440532013000\r\n")
    assert text.endswith("\r\n-")
    zeilen = text.split("\r\n")
    assert ":28C:1/1" in zeilen
    assert ":60F:D260630EUR50,00" in zeilen
    assert ":61:2607030703D1234,56NMSCNONREF" in zeilen
    assert ":62F:D260731EUR1284,56" in zeilen
    i = zeilen.index(":61:2607030703D1234,56NMSCNONREF")
    mehrzweck = zeilen[i + 1 : zeilen.index(":62F:D260731EUR1284,56")]
    assert mehrzweck[0].startswith(":86:999Miete Juli. Buero + Lager (Mueller) x")
    assert len(mehrzweck) == 6  # höchstens 6 Zeilen à 65 Zeichen
    assert len(mehrzweck[0]) == 4 + 65
    assert all(len(z) <= 65 for z in mehrzweck[1:])
    assert not any(z[:1] in {":", "-"} for z in mehrzweck[1:])


@pytest.mark.parametrize(
    ("roh", "erwartet"),
    [
        ("Größe Äpfel Öl Übung ß", "Groesse Aepfel Oel Uebung ss"),
        ("Café São Paulo", "Cafe Sao Paulo"),
        ("a@b.de; Rg #1 & 2 € {x}", "a b.de. Rg 1 + 2 EUR (x)"),
        ("Zeile\r\nZwei\t?", "Zeile Zwei"),
    ],
)
def test_swift_text(roh, erwartet):
    assert swift_text(roh) == erwartet


def test_kontobezeichnung():
    bank = Bankkonto(iban="DE89 3704 0044 0532 0130 00", bezeichnung="Haus")
    ausland = Bankkonto(iban="AT611904300234573201", bezeichnung="AT", sachkonto="1220")
    konten = [bank, ausland]
    assert kontobezeichnung("1200", konten, "1210", "PPLXLULL/PAYPAL") == (
        "37040044/532013000"
    )
    assert kontobezeichnung("1220", konten, "1210", "X") == "AT611904300234573201"
    assert kontobezeichnung("1210", konten, "1210", "PPLXLULL/PAYPAL") == (
        "PPLXLULL/PAYPAL"
    )
    with pytest.raises(KontoauszugError, match="--kontobezeichnung"):
        kontobezeichnung("1230", konten, "1210", "X")
    doppelt = [bank, Bankkonto(iban="DE02120300000000202051", bezeichnung="Zwei")]
    with pytest.raises(KontoauszugError, match="mehrere Bankkonten"):
        kontobezeichnung("1200", doppelt, "1210", "X")


def test_kontobezeichnung_aus_eingerichtetem_konto(s):
    speichere_bankkonto(s, Bankkonto(iban="DE02120300000000202051", bezeichnung="B"))
    bezeichnung = kontobezeichnung("1200", None, "1210", "X", session=s)
    assert bezeichnung == "12030000/202051"


def test_paypal_umsaetze_auf_eigenem_finanzkonto(s):
    _tx(s, date(2026, 7, 2), "49.90", konto="1210", quelle=TransaktionQuelle.PAYPAL)
    _tx(s, date(2026, 7, 3), "10.00")
    lauf = erstelle_auszuege(
        s, "1210", date(2026, 7, 31), anfangssaldo=D("0"), heute=HEUTE
    )
    assert lauf.neu[0].endsaldo == D("49.90")
    assert lade_kontoauszuege(s, "1200") == []


def test_erstellt_am_aus_parameter(s):
    jetzt = datetime(2026, 8, 1, 9, 0)
    lauf = _erstelle(s, date(2026, 7, 31), anfangssaldo=D("0"), jetzt=jetzt)
    assert lauf.neu[0].erstellt_am == jetzt
