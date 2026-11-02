"""Nachprüfung 6 E: fremde Umsätze und der Marktplatz-Abgleich.

Mb: opos-Zahlungsvorschlag und ``marktplatz zuordnen``; Mc: „schon gebucht“ nur mit
Stichwort oder Nummer, die Kasse ist keine Bank; Md: Umsätze eines anderen
Marktplatzes, mit der Nummer eines anderen oder einer Rechnung sind keine
Kandidaten; der festgeschriebene Monat; dazu die Niedrig-Befunde N-a bis N-i.
"""

from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest

from accounti.belege.archiv import BelegArchiv
from accounti.db import init_db, session_factory
from accounti.db.repo_integrationen import lade_abrechnungen
from accounti.db.repository import (
    buchungen_zur_transaktion,
    lade_buchungen,
    lade_zuordnungen,
    speichere_buchung,
    speichere_kontakt,
    speichere_posten,
    speichere_zuordnung,
)
from accounti.integrationen.auszahlung import (
    ZuordnungError,
    gleiche_auszahlungen_ab,
    ordne_zu,
)
from accounti.integrationen.einstellungen import lade_integrationen
from accounti.integrationen.lauf import Kontext
from accounti.konfiguration import Buchhaltung
from accounti.models import (
    Buchungssatz,
    BuchungStatus,
    Kontakt,
    OffenerPosten,
    PostenRichtung,
    Transaktion,
    TransaktionQuelle,
    Zahlungszuordnung,
    ZuordnungStatus,
)
from accounti.models.integrationen import Schweregrad
from accounti.opos.zahlungslauf import ZahlungslaufError, bestaetige
from tests.test_integrationen_lauf import (
    FIXTURES,
    _als_erloes_gebucht,
    _amazon_ende_august,
    _bank_lauf_mit_regel,
    _ustva_warnungen,
    amazon,
    bank,
    saldo,
)

EBAY = "EBAY MANAGED PAYMENTS"


@pytest.fixture
def umgebung(tmp_path):
    """Wie in ``test_integrationen_lauf``: leere Datenbank, Archiv, Standardkontext."""
    engine, make = session_factory(f"sqlite:///{tmp_path / 'm.db'}")
    init_db(engine)
    kontext = Kontext(
        einstellungen=lade_integrationen(tmp_path / "keine.yaml"),
        buchhaltung=Buchhaltung(),
        oss_registriert=True,
    )
    with make() as s:
        yield s, BelegArchiv(tmp_path / "archiv"), kontext


def _amazon_september(s, archiv, kontext):
    """Amazon 11223344556 (16.–31.08.), Auszahlung 209,85 € am 02.09."""
    roh = _amazon_ende_august((FIXTURES / "amazon_abrechnung_v2.txt").read_bytes())
    (ergebnis,) = amazon(s, archiv, kontext, roh)
    return ergebnis


def _forderung(s, belegnummer, betrag, kunde="Galerie Nord GmbH", tag=None):
    """Offene Ausgangsrechnung eines Kunden (opos)."""
    k = Kontakt(name=kunde, debitor_konto="10001")
    speichere_kontakt(s, k)
    p = OffenerPosten(
        kontakt_id=k.id,
        beleg_id=uuid4(),
        richtung=PostenRichtung.FORDERUNG,
        belegnummer=belegnummer,
        belegdatum=tag or date(2026, 8, 1),
        betrag=Decimal(betrag),
        faellig_am=tag or date(2026, 8, 15),
    )
    speichere_posten(s, p)
    s.flush()
    return p


def _vorschlag(s, tx, posten):
    """Ein Zahlungsvorschlag von opos (wie ``zuordne_zahlungen``, Stufe unscharf)."""
    speichere_zuordnung(
        s,
        Zahlungszuordnung(
            transaktion_id=tx.id,
            posten_id=posten.id,
            betrag=tx.betrag,
            stufe="unscharf",
            status=ZuordnungStatus.VORGESCHLAGEN,
            confidence=0.6,
            begruendung="Kontakt unbekannt, aber genau ein offener Posten",
        ),
    )
    s.flush()


def _befunde(s, nummer, *, hinweise=False):
    (a,) = [x for x in lade_abrechnungen(s) if x.nummer == nummer]
    return [
        b
        for b in a.offene_befunde
        if b.code.startswith(("auszahlung", "zuordnung"))
        and (hinweise or b.schweregrad is not Schweregrad.HINWEIS)
    ]


# --- Mb: opos-Zahlungsvorschlag ---------------------------------------------------


def test_zuordnen_lehnt_umsatz_mit_zahlungsvorschlag_ab(umgebung):
    """Mb (a): opos hat den Umsatz einer fremden Forderung vorgeschlagen; der
    automatische Abgleich lässt ihn deshalb liegen (``offen_ids``), ``marktplatz
    zuordnen`` nahm ihn trotzdem — nach dem Bestätigen war er doppelt gebucht. Die
    Meldung nennt den Befehl, der den Vorschlag verwirft."""
    s, archiv, kontext = umgebung
    _amazon_september(s, archiv, kontext)
    tx = bank(s, date(2026, 9, 3), "209.85", "AMAZON PAYMENTS EUROPE EREF 11223399999")
    _vorschlag(s, tx, _forderung(s, "RE-2026-77", "209.85"))
    gleiche_auszahlungen_ab(s, kontext)
    ident = str(tx.id)[:8]
    with pytest.raises(ZuordnungError, match=f"accounti opos ablehnen {ident}"):
        ordne_zu(s, kontext, "11223344556", ident, von="erika")
    assert not buchungen_zur_transaktion(s, tx.id)


def test_bestaetige_lehnt_inzwischen_gebuchten_umsatz_ab(umgebung):
    """Mb (b): Steht der Umsatz inzwischen anderweitig gebucht (hier: als
    Geldbewegung auf dem Amazon-Verrechnungskonto), bucht ``opos bestaetige`` ihn
    nicht ein zweites Mal gegen die Forderung."""
    s, archiv, kontext = umgebung
    posten = _forderung(s, "RE-2026-77", "209.85")
    tx = bank(s, date(2026, 9, 3), "209.85", "AMAZON PAYMENTS EUROPE")
    _vorschlag(s, tx, posten)
    speichere_buchung(
        s,
        Buchungssatz(
            transaktion_id=tx.id,
            datum=tx.datum,
            soll_konto="1200",
            haben_konto="1361",
            betrag_netto=Decimal("209.85"),
            buchungstext="Amazon Auszahlung",
            status=BuchungStatus.AUTO_GEBUCHT,
        ),
    )
    s.flush()
    with pytest.raises(ZahlungslaufError, match="schon gebucht"):
        bestaetige(s, str(tx.id)[:8], kontext.buchhaltung, von="erika")
    assert len(buchungen_zur_transaktion(s, tx.id)) == 1
    assert saldo(lade_buchungen(s), "10001") == 0


def test_bestaetige_lehnt_einer_auszahlung_zugeordneten_umsatz_ab(umgebung):
    """Mb (b): auch, wenn der Umsatz einer Marktplatz-Auszahlung zugeordnet ist."""
    s, archiv, kontext = umgebung
    posten = _forderung(s, "RE-2026-77", "209.85")
    _amazon_september(s, archiv, kontext)
    tx = bank(s, date(2026, 9, 3), "209.85", "AMAZON PAYMENTS EUROPE 11223344556")
    _vorschlag(s, tx, posten)
    # wie vor der Behebung (a): zugeordnet trotz Vorschlag
    from accounti.integrationen import auszahlung

    lauf = auszahlung._neuer_lauf(s, kontext, lade_abrechnungen(s))
    (a,) = lade_abrechnungen(s)
    (p,) = [x for x in a.posten if x.art.value == "auszahlung"]
    auszahlung._zuordnen(lauf, a, p, tx, Decimal("209.85"), von_hand=True)
    with pytest.raises(ZahlungslaufError, match="schon gebucht"):
        bestaetige(s, str(tx.id)[:8], kontext.buchhaltung, von="erika")


def test_bank_lauf_schlaegt_zurueckgehaltene_auszahlung_keiner_forderung_vor(umgebung):
    """Mb (c), Fall s14: Regel 4 hält die Amazon-Auszahlung zurück (Warnung mit dem
    zuordnen-Befehl), im selben ``bank lauf`` schlug opos sie einer fremden Forderung
    gleichen Betrags vor („Kontakt unbekannt, aber genau ein offener Posten“). Der
    Abgleich weiß, dass sie eine Auszahlung ist — opos lässt sie liegen."""
    s, archiv, kontext = umgebung
    _forderung(s, "RE-2026-77", "209.85", tag=date(2026, 8, 20))
    _amazon_september(s, archiv, kontext)
    tx = bank(
        s,
        date(2026, 9, 3),
        "209.85",
        "AMAZON PAYMENTS EUROPE EREF 11223399999",
        "Amazon Payments Europe S.C.A.",
    )
    lauf = _bank_lauf_mit_regel(s, kontext, r"AMAZON")
    (m,) = lauf.marktplatz
    assert m.befund is not None and m.befund.code == "auszahlung_andere_nummer"
    assert not lauf.zuordnung.vorgeschlagen and not lauf.zuordnung.gebucht
    assert not lade_zuordnungen(s)
    # der Befehl aus der Warnung geht jetzt ohne Umweg
    ordne_zu(s, kontext, "11223344556", str(tx.id)[:8], von="erika")
    assert saldo(lade_buchungen(s), "1200") == Decimal("209.85")
    assert saldo(lade_buchungen(s), "10001") == 0


# --- Mc: „schon gebucht“ nur mit Stichwort oder Nummer; die Kasse ist keine Bank -----


def _kassenvorgang(s, tag, betrag):
    """Ein Barverkauf im Kassenbuch (Quelle manuell, Sachkonto 1000, 1000 an 8400)."""
    from accounti.db.repository import speichere_transaktion

    t = Transaktion(
        datum=tag,
        betrag=Decimal(betrag),
        verwendungszweck="Barverkauf Bilderrahmen",
        quelle=TransaktionQuelle.MANUELL,
        rohtext="Kassenbuch Nr. 17: Barverkauf Bilderrahmen",
        sachkonto="1000",
    )
    speichere_transaktion(s, t)
    speichere_buchung(
        s,
        Buchungssatz(
            transaktion_id=t.id,
            datum=t.datum,
            soll_konto="1000",
            haben_konto="8400",
            betrag_netto=Decimal("176.34"),
            steuer_schluessel=3,
            steuer_betrag=Decimal("33.51"),
            buchungstext="Barverkauf",
            status=BuchungStatus.GEPRUEFT,
        ),
    )
    s.flush()
    return t


def test_kassenvorgang_ist_keine_auszahlung(umgebung):
    """Mc, Fall s19: ein Barverkauf im Kassenbuch über den Betrag der Amazon-
    Auszahlung bekam den FEHLER „schon gebucht – Erlöse wären doppelt“ mit
    ``korrigiere … --soll 1000 --haben 1361`` (der Befehl löschte echten Erlös samt
    USt), die UStVA 09 warnte. Eine Auszahlung geht auf die Bank, nie in die Kasse:
    Kassenbuch-Vorgänge sind keine Kandidaten (Regel 1, wie ``buchung.marktplatz``)."""
    s, archiv, kontext = umgebung
    _kassenvorgang(s, date(2026, 9, 3), "209.85")
    ergebnis = _amazon_september(s, archiv, kontext)
    assert not [a.befund for a in ergebnis.abgleich if a.befund]
    assert not _befunde(s, "11223344556", hinweise=True)
    assert not _ustva_warnungen(s, "2026-09")


def _paypal_mit_kundenzahlung(s, archiv, kontext):
    """Fall s20: eine Kundenzahlung über 150,00 € am 12.08. ist per Regel als Erlös
    gebucht; PayPal erwartet seine Auszahlung von 150 € (12./13.08.), deren
    Bankumsatz noch fehlt."""
    from tests.test_integrationen_lauf import paypal

    kunde = bank(
        s, date(2026, 8, 12), "150.00", "RE-2026-12 RAHMEN", "Galerie Nord GmbH"
    )
    _als_erloes_gebucht(s, kunde, "126.05", "23.95")
    bank(s, date(2026, 8, 19), "-50.00", "PAYPAL EUROPE GUTHABEN")
    (ergebnis,) = paypal(s, archiv, kontext)
    return kunde, ergebnis


def test_fremde_kundenzahlung_mit_dem_betrag_ist_kein_fehler(umgebung):
    """Mc, Fälle s20/s21: die Kundenzahlung nennt weder ein PayPal-Stichwort noch die
    Abrechnung. Seit ff68510 bekam sie den FEHLER „schon gebucht“ mit
    ``korrigiere … --soll 1200 --haben 1360`` — wer ihm folgte, hatte 8400 = 0
    (126,05 € Erlös und 23,95 € USt fehlten), PayPal war mit ihr abgeglichen und sein
    echter Umsatz blieb für immer offen. Ohne Stichwort und Nummer ist der Betrag
    allein höchstens ein Hinweis, ohne korrigiere-Befehl; kommt PayPals Umsatz, wird
    er Treffer und der Hinweis ist erledigt."""
    s, archiv, kontext = umgebung
    kunde, ergebnis = _paypal_mit_kundenzahlung(s, archiv, kontext)
    nummer = ergebnis.abrechnung.nummer
    assert not _befunde(s, nummer)  # kein Fehler, keine Warnung
    (hinweis,) = _befunde(s, nummer, hinweise=True)
    assert hinweis.code == "auszahlung_vielleicht_gebucht"
    assert hinweis.schweregrad is Schweregrad.HINWEIS
    assert "accounti korrigiere" not in hinweis.text and "--soll" not in hinweis.text
    assert not _ustva_warnungen(s, "2026-08")
    p = bank(s, date(2026, 8, 13), "150.00", "PAYPAL EUROPE ABBUCHUNG")
    gleiche_auszahlungen_ab(s, kontext)
    (a,) = lade_abrechnungen(s)
    assert p.id in {x.bank_transaktion_id for x in a.posten}
    assert kunde.id not in {x.bank_transaktion_id for x in a.posten}
    assert not _befunde(s, nummer, hinweise=True)
    (erloes,) = buchungen_zur_transaktion(s, kunde.id)
    assert (erloes.haben_konto, erloes.steuer_betrag) == ("8400", Decimal("23.95"))


def test_erkennbarer_umsatz_bleibt_schon_gebucht(umgebung):
    """Gegenprobe zu Mc: mit Stichwort (oder Nummer) bleibt es der FEHLER mit dem
    korrigiere-Befehl — dort ist der Umsatz erkennbar die Auszahlung."""
    s, archiv, kontext = umgebung
    tx = bank(s, date(2026, 9, 3), "209.85", "AMAZON PAYMENTS EUROPE")
    _als_erloes_gebucht(s, tx, "176.34", "33.51")
    _amazon_september(s, archiv, kontext)
    (b,) = _befunde(s, "11223344556")
    assert b.code == "auszahlung_anderweitig_gebucht" and "korrigiere" in b.text
    assert b.schweregrad is Schweregrad.FEHLER
    assert _ustva_warnungen(s, "2026-09")


# --- N-d: Kartenumsätze sind keine Kandidaten ------------------------------------


def _kartengutschrift(s, tag, betrag, zweck="AMAZON.DE ERSTATTUNG"):
    """Eine Gutschrift auf dem Kreditkartenkonto (Sachkonto 1290)."""
    from accounti.db.repo_bank import speichere_kreditkarte
    from accounti.db.repository import speichere_bankkonto
    from accounti.db.tabellen import TransaktionRow
    from accounti.models import Bankkonto
    from accounti.models.bank import Kreditkarte

    giro = Bankkonto(
        iban="DE02120300000000202051", bezeichnung="Giro", sachkonto="1200"
    )
    karte = Bankkonto(iban="KARTE-1234", bezeichnung="Visa", sachkonto="1290")
    speichere_bankkonto(s, giro)
    speichere_bankkonto(s, karte)
    speichere_kreditkarte(
        s, Kreditkarte(bankkonto_id=karte.id, girokonto_id=giro.id, endziffern="1234")
    )
    s.flush()
    t = bank(s, tag, betrag, zweck, "AMAZON")
    zeile = s.get(TransaktionRow, str(t.id))
    zeile.bankkonto_id = str(karte.id)
    zeile.sachkonto = "1290"
    s.flush()
    return t


def test_kartengutschrift_ist_keine_auszahlung(umgebung):
    """N-d, Fall s3: eine Amazon-Erstattung auf der Kreditkarte über den Betrag der
    Auszahlung wurde zugeordnet (1290 an 1361) — sie minderte weder Aufwand noch
    Vorsteuer. Eine Auszahlung geht nie auf eine Kreditkarte (wie
    ``buchung.marktplatz``)."""
    s, archiv, kontext = umgebung
    c = _kartengutschrift(s, date(2026, 9, 3), "209.85")
    ergebnis = _amazon_september(s, archiv, kontext)
    assert all(a.transaktion is None for a in ergebnis.abgleich)
    assert not buchungen_zur_transaktion(s, c.id)
    assert not _befunde(s, "11223344556", hinweise=True)
    with pytest.raises(ZuordnungError, match="Kein Bankumsatz"):
        ordne_zu(s, kontext, "11223344556", str(c.id)[:8], von="erika")


def test_kartengutschrift_nicht_im_befund_mehrdeutig(umgebung):
    """N-d, Fall s18: Kartengutschrift und Giro-Umsatz, beide ohne Nummer — der
    Befund „mehrdeutig“ bot die Karte als Bankumsatz an. Jetzt ist der Giro-Umsatz
    der einzige Kandidat."""
    s, archiv, kontext = umgebung
    _kartengutschrift(s, date(2026, 9, 3), "209.85")
    k = bank(s, date(2026, 9, 4), "209.85", "AMAZON PAYMENTS EUROPE")
    ergebnis = _amazon_september(s, archiv, kontext)
    (m,) = ergebnis.abgleich
    assert m.transaktion is not None and m.transaktion.id == k.id


# --- Md: Umsätze eines anderen Vorgangs sind keine Kandidaten ----------------------


def _paypal(s, archiv, kontext):
    """PayPal importiert: Auszahlung +150 € (12.08.), Einzahlung −50 € (20.08.)."""
    from tests.test_integrationen_lauf import paypal

    (ergebnis,) = paypal(s, archiv, kontext)
    return ergebnis.abrechnung.nummer


def _paypal_zugeordnet(s):
    (a,) = [x for x in lade_abrechnungen(s) if x.marktplatz == "paypal"]
    return {
        x.bank_transaktion_id for x in a.posten if x.bank_transaktion_id is not None
    }


def test_paypal_nimmt_keine_kundenzahlung_mit_rechnungsnummer(umgebung):
    """Md, Fall s22: PayPal importiert, bevor sein Bankumsatz kommt; ein Kunde zahlt
    RE-2026-12 über genau 150,00 €. Der Abgleich läuft in ``bank lauf`` vor opos
    (29d4801) und nahm die Kundenzahlung als PayPal-Auszahlung (1200/1360), ohne
    Befund — RE-2026-12 blieb offen (Mahnung droht), PayPals Umsatz für immer offen.
    Ein Umsatz mit der Nummer einer Rechnung (opos) ist keine Auszahlung."""
    s, archiv, kontext = umgebung
    _forderung(s, "RE-2026-12", "150.00")
    bank(s, date(2026, 8, 19), "-50.00", "PAYPAL EUROPE GUTHABEN")
    nummer = _paypal(s, archiv, kontext)
    kunde = bank(s, date(2026, 8, 14), "150.00", "RE-2026-12", "Galerie Nord GmbH")
    lauf = _bank_lauf_mit_regel(s, kontext, r"PAYPAL")
    assert kunde.id not in _paypal_zugeordnet(s)
    assert [b.haben_konto for b in buchungen_zur_transaktion(s, kunde.id)] == ["10001"]
    assert lauf.zuordnung.gebucht  # opos gleicht RE-2026-12 aus
    assert not _befunde(s, nummer, hinweise=True)
    p = bank(s, date(2026, 8, 16), "150.00", "PAYPAL EUROPE ABBUCHUNG")
    _bank_lauf_mit_regel(s, kontext, r"PAYPAL")
    assert p.id in _paypal_zugeordnet(s)
    assert not _befunde(s, nummer, hinweise=True)


def test_paypal_nimmt_keinen_umsatz_mit_fremdem_stichwort(umgebung):
    """Md, Fall s5: PayPal nahm „EBAY MANAGED PAYMENTS AUSZAHLUNG 6001234567“ als
    seine Auszahlung; der Import von eBay 6001234567 fand danach nichts (1362 =
    150 €), ohne Befund. Ein Umsatz mit dem Stichwort eines anderen Marktplatzes
    (und ohne das eigene) gehört nicht zu dieser Auszahlung."""
    from accounti.integrationen.lauf import importiere
    from tests.marktplatz_hilfe import ebay_bericht

    s, archiv, kontext = umgebung
    e = bank(s, date(2026, 8, 13), "150.00", f"{EBAY} AUSZAHLUNG 6001234567", "eBay")
    bank(s, date(2026, 8, 19), "-50.00", "PAYPAL EUROPE GUTHABEN")
    nummer = _paypal(s, archiv, kontext)
    assert e.id not in _paypal_zugeordnet(s)
    assert not _befunde(s, nummer)
    importiere(
        s,
        archiv,
        kontext,
        "ebay",
        ebay_bericht(
            (
                "10.08.2026",
                "Bestellung",
                "12-567",
                "Deutschland",
                "150,00",
                "6001234567",
                "",
            ),
            ("13.08.2026", "Auszahlung", "", "", "-150,00", "6001234567", "13.08.2026"),
        ),
        "e.csv",
    )
    assert e.id in {
        p.bank_transaktion_id
        for a in lade_abrechnungen(s)
        if a.nummer == "6001234567"
        for p in a.posten
    }
    assert saldo(lade_buchungen(s), "1362") == 0


def test_umsatz_mit_nummer_eines_anderen_marktplatzes_ist_kein_kandidat(umgebung):
    """Md: nennt der Umsatz die bekannte Nummer der Abrechnung eines anderen
    Marktplatzes (hier eBay, ohne Stichwort), ist er nicht PayPals Auszahlung —
    auch wenn eBay ihn selbst nicht nimmt (außerhalb ihres Fensters)."""
    from accounti.integrationen.lauf import importiere
    from tests.marktplatz_hilfe import ebay_bericht

    s, archiv, kontext = umgebung
    importiere(
        s,
        archiv,
        kontext,
        "ebay",
        ebay_bericht(
            (
                "01.07.2026",
                "Bestellung",
                "12-567",
                "Deutschland",
                "150,00",
                "6001234567",
                "",
            ),
            ("02.07.2026", "Auszahlung", "", "", "-150,00", "6001234567", "02.07.2026"),
        ),
        "e.csv",
    )
    x = bank(s, date(2026, 8, 13), "150.00", "GUTSCHRIFT 6001234567")
    bank(s, date(2026, 8, 19), "-50.00", "PAYPAL EUROPE GUTHABEN")
    _paypal(s, archiv, kontext)
    assert x.id not in _paypal_zugeordnet(s)


def test_paypal_nimmt_keine_lastschrift_einer_offenen_eingangsrechnung(umgebung):
    """Md (Gegenprüfung v7): PayPal erwartet die Einzahlung −50 € (20.08.), deren
    Lastschrift noch fehlt; die Telekom bucht 50,00 € für eine offene
    Eingangsrechnung ab. PayPal nahm sie (1360/1200) — Aufwand und Vorsteuer fehlten
    in der UStVA. Die Belegnummer eines offenen Postens schließt aus."""
    s, archiv, kontext = umgebung
    k = Kontakt(name="Telekom Deutschland GmbH", kreditor_konto="70001")
    speichere_kontakt(s, k)
    speichere_posten(
        s,
        OffenerPosten(
            kontakt_id=k.id,
            beleg_id=uuid4(),
            richtung=PostenRichtung.VERBINDLICHKEIT,
            belegnummer="RG 2026 0815 4711",
            belegdatum=date(2026, 8, 1),
            betrag=Decimal("50.00"),
            faellig_am=date(2026, 8, 20),
        ),
    )
    bank(s, date(2026, 8, 13), "150.00", "PAYPAL EUROPE ABBUCHUNG")
    t = bank(
        s,
        date(2026, 8, 19),
        "-50.00",
        "RG 2026 0815 4711 Mobilfunk",
        "Telekom Deutschland GmbH",
    )
    _paypal(s, archiv, kontext)
    assert t.id not in _paypal_zugeordnet(s)
    assert not buchungen_zur_transaktion(s, t.id)


def test_paypal_zuordnung_ohne_stichwort_ist_ein_hinweis(umgebung):
    """Md: bleibt ein Treffer ohne Stichwort (und ohne Nummer), ist die Zuordnung
    geraten — auch bei PayPal, dessen Abrechnung keine Nummer im Verwendungszweck
    hat, der Hinweis ``zuordnung_ohne_nummer`` (er fehlte dort immer)."""
    s, archiv, kontext = umgebung
    t = bank(s, date(2026, 8, 13), "150.00", "BAREINZAHLUNG")
    bank(s, date(2026, 8, 19), "-50.00", "PAYPAL EUROPE GUTHABEN")
    nummer = _paypal(s, archiv, kontext)
    assert t.id in _paypal_zugeordnet(s)
    (hinweis,) = _befunde(s, nummer, hinweise=True)
    assert hinweis.code == "zuordnung_ohne_nummer"
    assert "Stichwort" in hinweis.text and str(t.id)[:8] in hinweis.text
    assert "nach Betrag und Stichwort" not in hinweis.text


def test_paypal_mit_stichwort_ohne_hinweis(umgebung):
    """Gegenprobe: PayPals eigener Umsatz mit Stichwort bekommt keinen Hinweis — die
    PayPal-Abrechnung kann keine Nummer im Verwendungszweck haben."""
    s, archiv, kontext = umgebung
    bank(s, date(2026, 8, 13), "150.00", "PAYPAL EUROPE ABBUCHUNG")
    bank(s, date(2026, 8, 19), "-50.00", "PAYPAL EUROPE GUTHABEN")
    nummer = _paypal(s, archiv, kontext)
    assert not _befunde(s, nummer, hinweise=True)


# --- Robustheit: vorgebuchter Umsatz mit Kursdifferenz im festgeschriebenen Monat ---


def _schon_gebucht_september_zu(s, archiv, kontext):
    """Fall s17: A (nennt 6009990001, 59,75 € am 30.09.) per Regel als Erlös
    gebucht, der eBay-GBP-Import meldet „schon gebucht“; die Vorschläge werden
    freigegeben, September festgeschrieben, dann korrigiert der Mensch wie
    vorgeschlagen mit --datum 2026-10-01 (Bank an 1362)."""
    import re

    from accounti.pruefung.perioden import schliesse
    from accounti.pruefung.storno import VORSCHLAG, freigeben, korrigiere
    from tests.test_integrationen_lauf import _ebay_import

    a = bank(s, date(2026, 9, 30), "59.75", f"{EBAY} AUSZAHLUNG 6009990001", "eBay")
    _als_erloes_gebucht(s, a, "50.21", "9.54")
    _ebay_import(s, archiv, kontext)
    for b in lade_buchungen(s):
        if b.status in VORSCHLAG:
            freigeben(s, str(b.id), von="erika")
    schliesse(s, "2026-09", "erika", trotzdem=True)
    (befund,) = _befunde(s, "6009990001")
    ident, soll, haben = re.search(
        r"korrigiere (\w+) --soll (\d+) --haben (\d+)", befund.text
    ).groups()
    korrigiere(
        s, ident, soll, haben, ohne_steuer=True, von="erika", datum=date(2026, 10, 1)
    )
    s.flush()
    return a


def test_kursdifferenz_eines_umsatzes_im_festgeschriebenen_monat(umgebung):
    """Robustheit, Fall s17: der korrigierte Umsatz (30.09.) steht als Geldbewegung
    auf 1362, die Abrechnung erwartet 59,73 € — die Kursdifferenz von 0,02 € buchte
    der Abgleich am Tag des Umsatzes, im festgeschriebenen September: jeder Abgleich,
    jeder ``bank lauf`` und jeder Marktplatz-Import brach mit PeriodeGesperrtError
    ab. Die Kursdifferenz geht wie die Korrektur selbst in den ersten offenen Tag
    desselben Geschäftsjahres, der Hinweis nennt den Tag und den Monat."""
    from accounti.integrationen.lauf import importiere
    from tests.test_integrationen_lauf import _ebay_gbp

    s, archiv, kontext = umgebung
    a = _schon_gebucht_september_zu(s, archiv, kontext)
    (m,) = gleiche_auszahlungen_ab(s, kontext)
    assert m.transaktion is not None and m.transaktion.id == a.id
    assert m.befund is not None and m.befund.code == "kursdifferenz"
    assert "01.10.2026" in m.befund.text and "2026-09" in m.befund.text
    buchungen = lade_buchungen(s)
    (kurs,) = [b for b in buchungen if "Kursdifferenz" in b.buchungstext]
    assert kurs.datum == date(2026, 10, 1)
    assert saldo(buchungen, "1362") == 0
    assert not _befunde(s, "6009990001")
    _bank_lauf_mit_regel(s, kontext)
    # der Import einer anderen Abrechnung gleicht alle ab — ohne Abbruch
    importiere(
        s,
        archiv,
        kontext,
        "ebay",
        _ebay_gbp(zweite=True),
        "gbp2.csv",
        kurs=Decimal("0.8650"),
        buchungsdatum="offen",
    )
    # lösen storniert auch die verschobene Kursdifferenz
    ordne_zu(s, kontext, "6009990001", None, von="erika")
    assert saldo(lade_buchungen(s), "2660") == 0


def test_offener_umsatz_im_festgeschriebenen_monat_zuordnen(umgebung):
    """Ein offener Umsatz in einem festgeschriebenen Monat: ``marktplatz zuordnen``
    bricht nicht mit PeriodeGesperrtError ab, sondern sagt, was zu tun ist (die
    Bankbuchung gehört auf den Tag des Umsatzes)."""
    from accounti.pruefung.perioden import schliesse

    s, archiv, kontext = umgebung
    _amazon_september(s, archiv, kontext)
    tx = bank(s, date(2026, 9, 3), "209.85", "AMAZON PAYMENTS EUROPE EREF 11223399999")
    from accounti.pruefung.storno import VORSCHLAG, freigeben

    for b in lade_buchungen(s):
        if b.status in VORSCHLAG:
            freigeben(s, str(b.id), von="erika")
    schliesse(s, "2026-09", "erika", trotzdem=True)
    with pytest.raises(ZuordnungError, match="2026-09.*periode oeffnen"):
        ordne_zu(s, kontext, "11223344556", str(tx.id)[:8], von="erika")


def test_kursdifferenz_ohne_offenen_tag_im_geschaeftsjahr_ist_befund(umgebung):
    """Robustheit: ist bis zum Jahresende kein Tag offen, bleibt die Kursdifferenz
    im Geschäftsjahr der Auszahlung (§ 252 Abs. 1 Nr. 5 HGB) — der Umsatz wird nicht
    Treffer, die Warnung ``auszahlung_gesperrt`` nennt den Zeitraum; Abgleich und
    ``marktplatz zuordnen`` brechen nicht ab."""
    from accounti.pruefung.perioden import schliesse
    from accounti.pruefung.storno import VORSCHLAG, freigeben

    s, archiv, kontext = umgebung
    a = _schon_gebucht_september_zu(s, archiv, kontext)
    for b in lade_buchungen(s):
        if b.status in VORSCHLAG:
            freigeben(s, str(b.id), von="erika")
    for monat in ("2026-10", "2026-11", "2026-12"):
        schliesse(s, monat, "erika", trotzdem=True)
    (m,) = gleiche_auszahlungen_ab(s, kontext)
    assert m.transaktion is None
    assert m.befund is not None and m.befund.code == "auszahlung_gesperrt"
    assert "2026-09" in m.befund.text and str(a.id)[:8] in m.befund.text
    with pytest.raises(ZuordnungError, match="abgeschlossenen Zeitraum"):
        ordne_zu(s, kontext, "6009990001", str(a.id)[:8], von="erika")
    _bank_lauf_mit_regel(s, kontext)  # bricht nicht ab


# --- Niedrig: N-a bis N-i ---------------------------------------------------------


def test_gedruckter_zuordnen_befehl_ist_ausfuehrbar(umgebung):
    """N-a: die Nummer einer PayPal-Abrechnung hat Leerzeichen („PayPal 2026-08-02
    bis 2026-08-20“) — ohne Anführungszeichen endete der gedruckte Befehl mit „Got
    unexpected extra argument(s)“. Shell-Wörter wie gedruckt ergeben Nummer und
    Umsatz."""
    import re
    import shlex

    s, archiv, kontext = umgebung
    erster = bank(s, date(2026, 8, 13), "150.00", "PAYPAL EUROPE ABBUCHUNG")
    bank(s, date(2026, 8, 14), "150.00", "PAYPAL EUROPE ABBUCHUNG")
    bank(s, date(2026, 8, 19), "-50.00", "PAYPAL EUROPE GUTHABEN")
    nummer = _paypal(s, archiv, kontext)
    (b,) = _befunde(s, nummer)
    assert b.code == "auszahlung_mehrdeutig", b.text
    befehl = re.search(
        r"accounti marktplatz zuordnen .*? [0-9a-f]{8}(?: --posten \d+)?", b.text
    )[0]
    _, _, _, gegeben, umsatz, *rest = shlex.split(befehl)
    assert gegeben == nummer
    # PayPal hat Aus- und Einzahlung — der Befehl nennt die Zeile
    assert rest[0] == "--posten"
    ordne_zu(s, kontext, gegeben, umsatz, posten=int(rest[1]), von="erika")
    assert {str(x)[:8] for x in _paypal_zugeordnet(s)} >= {umsatz}
    assert erster.id in _paypal_zugeordnet(s) or umsatz != str(erster.id)[:8]


def test_eigene_nummer_entscheidet_ueber_marktplaetze(umgebung):
    """N-b, Fall s12: PayPal und eBay 6001234567 erwarten je 150 €, der Umsatz nennt
    6001234567 — beide meldeten „mehrdeutig“ („kein Verwendungszweck nennt die
    Nummer“, falsch). Die eigene Nummer geht vor: eBay bekommt ihn."""
    from accounti.integrationen.lauf import importiere
    from tests.marktplatz_hilfe import ebay_bericht

    s, archiv, kontext = umgebung
    bank(s, date(2026, 8, 19), "-50.00", "PAYPAL EUROPE GUTHABEN")
    pp = _paypal(s, archiv, kontext)
    importiere(
        s,
        archiv,
        kontext,
        "ebay",
        ebay_bericht(
            (
                "10.08.2026",
                "Bestellung",
                "12-567",
                "Deutschland",
                "150,00",
                "6001234567",
                "",
            ),
            ("13.08.2026", "Auszahlung", "", "", "-150,00", "6001234567", "13.08.2026"),
        ),
        "e.csv",
    )
    e = bank(s, date(2026, 8, 13), "150.00", f"{EBAY} AUSZAHLUNG 6001234567", "eBay")
    _bank_lauf_mit_regel(s, kontext, r"PAYPAL|EBAY")
    assert e.id not in _paypal_zugeordnet(s)
    assert not _befunde(s, pp) and not _befunde(s, "6001234567")
    assert saldo(lade_buchungen(s), "1362") == 0


def test_zuordnen_prueft_das_datum(umgebung):
    """N-c, Fall s2: Amazon-Auszahlung vom 02.09.2026 — ``marktplatz zuordnen`` nahm
    einen Umsatz vom 15.03.2027 und einen vom 01.06.2026 (vor dem
    Abrechnungszeitraum). Vor dem Zeitraum ist er nie die Auszahlung; außerhalb des
    Fensters nur ausdrücklich (``trotzdem``: die Bank hat spät gebucht)."""
    s, archiv, kontext = umgebung
    _amazon_september(s, archiv, kontext)
    spaet = bank(s, date(2027, 3, 15), "209.85", "AMAZON PAYMENTS EUROPE")
    frueh = bank(s, date(2026, 6, 1), "209.85", "AMAZON PAYMENTS EUROPE")
    with pytest.raises(ZuordnungError, match="vor dem Abrechnungszeitraum"):
        ordne_zu(s, kontext, "11223344556", str(frueh.id)[:8], von="erika")
    with pytest.raises(ZuordnungError, match="--trotzdem"):
        ordne_zu(s, kontext, "11223344556", str(spaet.id)[:8], von="erika")
    with pytest.raises(ZuordnungError, match="vor dem Abrechnungszeitraum"):
        ordne_zu(
            s, kontext, "11223344556", str(frueh.id)[:8], von="erika", trotzdem=True
        )
    ordne_zu(s, kontext, "11223344556", str(spaet.id)[:8], von="erika", trotzdem=True)
    (a,) = lade_abrechnungen(s)
    assert spaet.id in {p.bank_transaktion_id for p in a.posten}


def test_journal_auch_fuer_den_mitgeloesten_posten(umgebung):
    """N-e, Fall s11: 6009990001 hat B (ohne Nummer), ``ordne_zu 6009990002 B`` löst
    diese Zuordnung mit — im Journal stand nur der Zielposten."""
    from accounti.pruefung.journal import lade_journal
    from accounti.pruefung.person import journal_kontext
    from tests.test_integrationen_lauf import _ebay_import

    s, archiv, kontext = umgebung
    b = bank(s, date(2026, 10, 2), "60.14", f"{EBAY} AUSZAHLUNG", "eBay")
    _ebay_import(s, archiv, kontext)
    _ebay_import(s, archiv, kontext, zweite=True)
    with journal_kontext(person="erika"):
        ordne_zu(s, kontext, "6009990002", str(b.id)[:8], von="erika")
    (x,) = [a for a in lade_abrechnungen(s) if a.nummer == "6009990001"]
    (p,) = [p for p in x.posten if p.art.value == "auszahlung"]
    (eintrag,) = lade_journal(s, objekt_id=str(p.id))
    import json

    assert eintrag.vorgang == "auszahlung_geloest"
    assert json.loads(eintrag.vorher)["bank_transaktion_id"] == str(b.id)
    assert json.loads(eintrag.nachher)["bank_transaktion_id"] is None
    assert "6009990002" in (eintrag.grund or "")


def test_loesen_warnt_bei_schon_an_datev_uebergebener_buchung(umgebung):
    """N-f, Fall s24: die Bankbuchung ist ein Vorschlag (Abrechnung mit Fehler) und
    ging mit ``export datev --alle`` schon an DATEV; ``--loesen`` verwarf sie ohne
    Warnung — DATEV behielt 1200 an 1361. Wie ``korrigiere``: die Warnung nennt den
    Stapel und den Weg."""
    from accounti.db.repo_integrationen import ergaenze_befunde
    from accounti.models.integrationen import Befund
    from accounti.pruefung.storno import markiere_exportiert

    s, archiv, kontext = umgebung
    e = _amazon_september(s, archiv, kontext)
    ergaenze_befunde(
        s,
        e.abrechnung.id,
        [
            Befund(
                code="summe_abweichung",
                schweregrad=Schweregrad.FEHLER,
                text="Summe der Einzelposten ≠ Auszahlung (simuliert)",
            )
        ],
    )
    s.flush()
    k = bank(s, date(2026, 9, 3), "209.85", "AMAZON PAYMENTS EUROPE 11223344556")
    gleiche_auszahlungen_ab(s, kontext)
    (b,) = buchungen_zur_transaktion(s, k.id)
    assert b.status is BuchungStatus.ZUR_PRUEFUNG
    markiere_exportiert(s, lade_buchungen(s), None, "datev")
    s.flush()
    erg = ordne_zu(s, kontext, "11223344556", None, von="erika")
    assert any(
        "DATEV" in w and "1200 an 1361" in w and "--erneut --alle" in w
        for w in erg.warnungen
    ), erg.warnungen


def test_loesen_nennt_die_geldbewegung_auf_dem_verrechnungskonto(umgebung):
    """N-i, Fall s16: nach „schon gebucht“ und der Korrektur des Menschen (Bank an
    1362) löst ``--loesen`` die Zuordnung; die Geldbewegung bleibt auf 1362 stehen,
    die Ausgabe sagte es nicht."""
    import re

    from accounti.pruefung.storno import korrigiere
    from tests.test_integrationen_lauf import _ebay_import

    s, archiv, kontext = umgebung
    a = bank(s, date(2026, 9, 30), "59.75", f"{EBAY} AUSZAHLUNG 6009990001", "eBay")
    _als_erloes_gebucht(s, a, "50.21", "9.54")
    _ebay_import(s, archiv, kontext)
    (befund,) = _befunde(s, "6009990001")
    ident, soll, haben = re.search(
        r"korrigiere (\w+) --soll (\d+) --haben (\d+)", befund.text
    ).groups()
    korrigiere(s, ident, soll, haben, ohne_steuer=True, von="erika")
    gleiche_auszahlungen_ab(s, kontext)
    erg = ordne_zu(s, kontext, "6009990001", None, von="erika")
    assert any("1362" in w and "Geldbewegung" in w for w in erg.warnungen), (
        erg.warnungen
    )


@pytest.mark.parametrize(
    "zweck",
    [
        "EBAY RECHNUNGSNUMMER 6009990077",
        "EBAY BESTELLNR 6009990077",
        "EBAY ORDER 6009990077",
        "EBAY INV 6009990077",
        "EBAY CUSTOMER 6009990077",
        "EBAY REF 6009990077",
        "EBAY BELEG 6009990077",
        "EBAY END-TO-END-REF 6009990077",
        "EBAY BESTELLNUMMER 6009990077",
        "EBAY INVOICE 6009990077",
    ],
)
def test_regel4_rechnungs_und_bestellangaben_sind_keine_auszahlungsnummer(zweck):
    """N-h, Fall s9: hinter einer Rechnungs-, Bestell-, Kunden- oder
    Referenzangabe ist eine Zahl keine Auszahlungsnummer (Regel 4)."""
    from accounti.integrationen.auszahlung import _andere_nummern
    from accounti.models.integrationen import Abrechnung

    a = Abrechnung.model_construct(nummer="6009990001", marktplatz="ebay")
    t = Transaktion(
        datum=date(2026, 9, 30),
        betrag=Decimal("1"),
        verwendungszweck=zweck,
        quelle=TransaktionQuelle.BANK,
        rohtext=zweck,
    )
    assert _andere_nummern(a, t) == []


@pytest.mark.parametrize(
    "zweck",
    [
        "EBAY EREF 6009990077",
        "EBAY AUSZAHLUNG 6009990077",
        "EBAY MANAGED PAYMENTS 6009990077",
        "EBAY NR 6009990077",
    ],
)
def test_regel4_auszahlungsnummern_bleiben(zweck):
    """Gegenprobe zu N-h: EREF (Marktplätze setzen dort ihre Auszahlungsnummer) und
    eine Nummer ohne Bezeichnung zählen weiter."""
    from accounti.integrationen.auszahlung import _andere_nummern
    from accounti.models.integrationen import Abrechnung

    a = Abrechnung.model_construct(nummer="6009990001", marktplatz="ebay")
    t = Transaktion(
        datum=date(2026, 9, 30),
        betrag=Decimal("1"),
        verwendungszweck=zweck,
        quelle=TransaktionQuelle.BANK,
        rohtext=zweck,
    )
    assert _andere_nummern(a, t) == ["6009990077"]


def test_classify_kontiert_keinen_umsatz_mit_abgleichsbefund(tmp_path, monkeypatch):
    """N-g, Fall s8: Regel 4 hält den Umsatz zurück (EREF mit dem Anfang der Amazon-
    Nummern), der Beleg-Abgleich hat ihm einen Beleg bestätigt. ``bank lauf`` ließ
    ihn offen, ``accounti classify`` buchte ihn aus dem Beleg (4900/1200 mit
    Vorsteuer) — der Docstring sagte das Gegenteil. classify lässt jetzt offen,
    worüber der Abgleich einen Befund hätte (ohne selbst abzugleichen)."""
    from typer.testing import CliRunner

    from accounti.cli import app
    from accounti.db.repository import speichere_abgleich, speichere_beleg
    from accounti.integrationen.einstellungen import lade_kontext
    from accounti.models import AbgleichStatus, Belegabgleich
    from tests.test_bank_abgleich import quittung

    monkeypatch.setenv("ACCOUNTI_KONFIG", str(tmp_path / "fehlt.yaml"))
    for name in ("ACCOUNTI_DB", "ACCOUNTI_GESELLSCHAFT", "ACCOUNTI_EINMALCODE"):
        monkeypatch.delenv(name, raising=False)
    url = f"sqlite:///{tmp_path / 'c.db'}"
    config = str(tmp_path / "fehlt.yaml")
    engine, make = session_factory(url)
    init_db(engine)
    kontext = lade_kontext(config)
    with make() as s:
        _amazon_september(s, BelegArchiv(tmp_path / "archiv"), kontext)
        tx = bank(
            s,
            date(2026, 9, 3),
            "209.85",
            "AMAZON PAYMENTS EUROPE EREF 11223399999",
            "Amazon Payments Europe S.C.A.",
        )
        beleg = quittung(
            brutto="209.85",
            netto=Decimal("176.34"),
            steuer=Decimal("33.51"),
            lieferant_name="Amazon Payments Europe S.C.A.",
            belegdatum=date(2026, 9, 3),
        )
        speichere_beleg(s, beleg)
        speichere_abgleich(
            s,
            Belegabgleich(
                transaktion_id=tx.id,
                beleg_id=beleg.id,
                stufe="exakt",
                status=AbgleichStatus.BESTAETIGT,
                confidence=1.0,
                begruendung="Test",
            ),
        )
        s.commit()
        vorher = len(lade_buchungen(s))
    engine.dispose()
    r = CliRunner().invoke(
        app, ["classify", "--db", url, "--no-llm", "--config", config]
    )
    assert r.exit_code == 0, r.output
    assert "Marktplatz" in r.output, r.output
    engine, make = session_factory(url)
    with make() as s:
        assert not buchungen_zur_transaktion(s, tx.id)
        assert len(lade_buchungen(s)) == vorher  # classify gleicht nicht ab
        (a,) = lade_abrechnungen(s)
        assert all(p.bank_transaktion_id is None for p in a.posten)
    engine.dispose()
