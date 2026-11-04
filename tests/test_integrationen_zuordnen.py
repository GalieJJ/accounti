"""Nachprüfung 5 E: Bankreferenz derselben Form (M4), Zuordnung von Hand (M4 c, N1),
eigene Nummer außerhalb der Toleranz (N2), umstrittener Umsatz ohne Nummer."""

from datetime import date, datetime
from decimal import Decimal

import pytest
from typer.testing import CliRunner

from accounti.belege.archiv import BelegArchiv
from accounti.db import init_db, session_factory
from accounti.db.repo_integrationen import lade_abrechnungen
from accounti.db.repository import (
    buchungen_zur_transaktion,
    lade_buchungen,
    speichere_abgleich,
    speichere_beleg,
)
from accounti.integrationen.auszahlung import (
    ZuordnungError,
    gleiche_auszahlungen_ab,
    ordne_zu,
)
from accounti.integrationen.einstellungen import lade_integrationen
from accounti.integrationen.lauf import Kontext
from accounti.konfiguration import Buchhaltung
from accounti.models import AbgleichStatus, Belegabgleich
from accounti.models.integrationen import AbrechnungStatus, Schweregrad
from tests.test_bank_abgleich import quittung
from tests.test_integrationen_lauf import (
    FIXTURES,
    _als_erloes_gebucht,
    _amazon_ende_august,
    _bank_lauf_mit_regel,
    _ebay_gbp,
    _ebay_import,
    _korrigiere_wie_vorgeschlagen,
    _ohne_stichwort,
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
        oss_roh=True,
    )
    with make() as s:
        yield s, BelegArchiv(tmp_path / "archiv"), kontext


def _amazon_september(s, archiv, kontext):
    """Amazon 11223344556 (16.–31.08.), Auszahlung 209,85 € am 02.09."""
    roh = _amazon_ende_august((FIXTURES / "amazon_abrechnung_v2.txt").read_bytes())
    (ergebnis,) = amazon(s, archiv, kontext, roh)
    return ergebnis


def _offene(s, nummer):
    (a,) = [x for x in lade_abrechnungen(s) if x.nummer == nummer]
    return [
        b
        for b in a.offene_befunde
        if b.code.startswith("auszahlung") and b.schweregrad is not Schweregrad.HINWEIS
    ]


def _zugeordnet(s):
    return {
        a.nummer: p.bank_transaktion_id
        for a in lade_abrechnungen(s)
        for p in a.posten
        if p.bank_transaktion_id is not None
    }


# --- M4: Regel 4 nur für Auszahlungsnummern, nicht für Bankreferenzen -------------


def test_r4a_ebay_eref_ist_keine_fremde_auszahlungsnummer(umgebung):
    """M4, Fall r4a: Abrechnung 6009990001 (GBP) importiert, dann die Bank mit
    „EREF 4711000815“ statt der Nummer, dann ``bank lauf``. Regel 4 hielt die Zahl
    gleicher Länge für die Nummer einer noch nicht importierten Abrechnung: nicht
    zugeordnet, die Regel buchte sie als Erlös (die UStVA 09 schwieg). Eine Zahl mit
    anderem Anfang ist keine Auszahlungsnummer desselben Marktplatzes."""
    s, archiv, kontext = umgebung
    _ebay_import(s, archiv, kontext)
    a = bank(s, date(2026, 9, 30), "59.75", f"{EBAY} EREF 4711000815", "eBay S.a.r.l.")
    ergebnis = _bank_lauf_mit_regel(s, kontext)
    (m,) = ergebnis.marktplatz
    assert m.transaktion is not None and m.transaktion.id == a.id
    assert ergebnis.kontierung.kontiert == 0
    assert saldo(lade_buchungen(s), "1362") == 0
    assert not _ustva_warnungen(s, "2026-09")


@pytest.mark.parametrize("stichwort", [True, False], ids=["stichwort", "ohne"])
def test_r4b_amazon_kundennummer_ist_keine_fremde_auszahlungsnummer(
    umgebung, stichwort
):
    """M4, Fall r4b: Amazon 11223344556 (16.–31.08.) importiert, die Bank zahlt am
    03.09. 209,85 € mit „KD 40123456789“, dann ``bank lauf``. Eine Kundennummer ist
    keine Abrechnungsnummer — der exakte Betrag ordnet zu (ohne ``bank_stichworte``
    blieb sie still offen, mit buchte die Regel sie vor dem Zusammenführen als
    Erlös)."""
    s, archiv, kontext = umgebung
    if not stichwort:
        kontext = _ohne_stichwort(kontext, "amazon")
    _amazon_september(s, archiv, kontext)
    tx = bank(s, date(2026, 9, 3), "209.85", "AMAZON PAYMENTS EUROPE KD 40123456789")
    ergebnis = _bank_lauf_mit_regel(s, kontext, r"AMAZON")
    (m,) = ergebnis.marktplatz
    assert m.transaktion is not None and m.transaktion.id == tx.id
    assert ergebnis.kontierung.kontiert == 0
    assert saldo(lade_buchungen(s), "1361") == 0
    assert not _ustva_warnungen(s, "2026-09")


def test_auszahlungsnummer_als_eref_bleibt_fremd(umgebung):
    """Gegenprobe zu M4 (M3 bleibt behoben): B nennt „EREF 6009990002“ — dieselbe
    Form und derselbe Anfang wie 6009990001, die Auszahlung einer noch nicht
    importierten Abrechnung. 6009990001 nimmt ihn nicht (Warnung), der Import von
    6009990002 ordnet ihn dort zu und erledigt die Warnung."""
    s, archiv, kontext = umgebung
    b = bank(s, date(2026, 10, 2), "60.14", f"{EBAY} EREF 6009990002", "eBay")
    (x,) = _ebay_import(s, archiv, kontext).abgleich
    assert x.transaktion is None and x.befund is not None
    assert x.befund.code == "auszahlung_andere_nummer", x.befund.text
    assert f"accounti marktplatz zuordnen 6009990001 {str(b.id)[:8]}" in x.befund.text
    _ebay_import(s, archiv, kontext, zweite=True)
    assert _zugeordnet(s) == {"6009990002": b.id}
    assert not _offene(s, "6009990001")


# --- M4 (a): kein Umsatz mit Abgleichsbefund wird im selben Lauf kontiert ---------


def test_bank_lauf_kontiert_keinen_umsatz_mit_abgleichsbefund(umgebung):
    """M4 (a): Regel 4 hält den Umsatz zurück (EREF mit dem Anfang der Amazon-
    Nummern), der Beleg-Abgleich hat ihm einen Beleg zugeordnet — die Kontierung
    buchte ihn aus dem Beleg, die UStVA schwieg. Was der Abgleich desselben Laufs mit
    einem Befund belegt, bleibt offen."""
    s, archiv, kontext = umgebung
    _amazon_september(s, archiv, kontext)
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
    s.flush()
    ergebnis = _bank_lauf_mit_regel(s, kontext, r"AMAZON")
    (m,) = ergebnis.marktplatz
    assert m.befund is not None and m.befund.code == "auszahlung_andere_nummer"
    assert ergebnis.kontierung.kontiert == 0
    assert ergebnis.kontierung.marktplatz == 1
    assert not buchungen_zur_transaktion(s, tx.id)


# --- M4 (c): Zuordnung von Hand ---------------------------------------------------


def _amazon_mit_referenz(s, archiv, kontext):
    """Amazon 11223344556 importiert, die Bank nennt eine Referenz mit dem Anfang
    der Amazon-Nummern — Regel 4 hält sie zurück (Warnung)."""
    _amazon_september(s, archiv, kontext)
    tx = bank(s, date(2026, 9, 3), "209.85", "AMAZON PAYMENTS EUROPE EREF 11223399999")
    (m,) = gleiche_auszahlungen_ab(s, kontext)
    assert m.transaktion is None and m.befund is not None
    assert m.befund.code == "auszahlung_andere_nummer", m.befund.text
    return tx, m.befund


def test_zuordnen_ordnet_den_zurueckgehaltenen_umsatz_zu(umgebung):
    """M4 (c): Die Warnung nennt den Befehl; ``ordne_zu`` bucht Bank an
    Verrechnungskonto, erledigt die Warnung und schreibt das Journal."""
    from accounti.pruefung.journal import lade_journal
    from accounti.pruefung.person import journal_kontext

    s, archiv, kontext = umgebung
    tx, befund = _amazon_mit_referenz(s, archiv, kontext)
    befehl = f"accounti marktplatz zuordnen 11223344556 {str(tx.id)[:8]}"
    assert befehl in befund.text
    with journal_kontext(person="erika"):
        ergebnis = ordne_zu(s, kontext, "11223344556", str(tx.id)[:8], von="erika")
    assert ergebnis.transaktion is not None and ergebnis.transaktion.id == tx.id
    (b,) = buchungen_zur_transaktion(s, tx.id)
    assert (b.soll_konto, b.haben_konto, b.steuer_schluessel) == ("1200", "1361", None)
    (a,) = lade_abrechnungen(s)
    assert a.status is AbrechnungStatus.ABGEGLICHEN
    assert not [x for x in a.offene_befunde if x.code == "auszahlung_andere_nummer"]
    assert saldo(lade_buchungen(s), "1361") == 0
    (p,) = [p for p in a.posten if p.bank_transaktion_id]
    (eintrag,) = lade_journal(s, objekt_id=str(p.id))
    assert eintrag.vorgang == "auszahlung_zugeordnet" and "erika" in eintrag.person
    # der nächste Abgleich lässt es dabei
    assert not [x for x in gleiche_auszahlungen_ab(s, kontext) if x.befund]
    assert _zugeordnet(s) == {"11223344556": tx.id}


def test_zuordnen_verlangt_erst_die_korrektur_eines_erloeses(umgebung):
    """Ein als Erlös gebuchter Umsatz wird nicht still umgebucht: die Meldung nennt
    den korrigiere-Befehl; danach ordnet ``ordne_zu`` ihn zu."""
    s, archiv, kontext = umgebung
    tx = bank(s, date(2026, 9, 3), "209.85", "AMAZON PAYMENTS EUROPE EREF 11223399999")
    _als_erloes_gebucht(s, tx, "176.34", "33.51")
    (ergebnis,) = [_amazon_september(s, archiv, kontext)]
    (befund,) = [a.befund for a in ergebnis.abgleich if a.befund]
    assert befund.code == "auszahlung_anderweitig_gebucht", befund.text
    assert f"marktplatz zuordnen <Nummer> {str(tx.id)[:8]}" in befund.text
    with pytest.raises(ZuordnungError, match="accounti korrigiere"):
        ordne_zu(s, kontext, "11223344556", str(tx.id)[:8], von="erika")
    _korrigiere_wie_vorgeschlagen(s, befund)
    # nach der Korrektur gleicht schon der Abgleich ab (die Geldbewegung steht auf
    # dem Verrechnungskonto) — Regel 4 hält nur offene Umsätze zurück
    gleiche_auszahlungen_ab(s, kontext)
    assert _zugeordnet(s) == {"11223344556": tx.id}
    assert not _ustva_warnungen(s, "2026-09")


def test_zuordnen_verweigert_falschen_betrag_und_falsche_richtung(umgebung):
    s, archiv, kontext = umgebung
    _amazon_september(s, archiv, kontext)
    anders = bank(s, date(2026, 9, 3), "199.85", "AMAZON PAYMENTS EUROPE")
    zurueck = bank(s, date(2026, 9, 3), "-209.85", "AMAZON PAYMENTS EUROPE")
    with pytest.raises(ZuordnungError, match="199,85"):
        ordne_zu(s, kontext, "11223344556", str(anders.id)[:8], von="erika")
    with pytest.raises(ZuordnungError, match="Richtung"):
        ordne_zu(s, kontext, "11223344556", str(zurueck.id)[:8], von="erika")
    assert not _zugeordnet(s)


# --- N1: Regel 8 — die frühere Zuordnung ohne Nummer lösen --------------------------


@pytest.mark.parametrize("gebucht", [False, True], ids=["offen", "als_erloes"])
def test_zuordnen_loest_die_zuordnung_ohne_nummer(umgebung, gebucht):
    """N1 (Fall v2): B ohne Nummer offen, 6009990001 nimmt ihn (damals nannte keiner
    die Nummer); dann kommt A mit der Nummer, dann 6009990002. 6009990002 fand
    nichts, 6009990001 blieb mit B zugeordnet — 1362 mit Rest, 6009990002 für immer
    „gebucht“. Der Befund an 6009990001 nennt jetzt den Befehl; er ordnet A zu, B
    wird frei und gehört danach 6009990002 — beide abgeglichen, 1362 = 0."""
    s, archiv, kontext = umgebung
    b = bank(s, date(2026, 10, 2), "60.14", f"{EBAY} AUSZAHLUNG", "eBay S.a.r.l.")
    (x,) = _ebay_import(s, archiv, kontext).abgleich
    assert x.transaktion is not None and x.transaktion.id == b.id
    a = bank(s, date(2026, 9, 30), "59.75", f"{EBAY} AUSZAHLUNG 6009990001", "eBay")
    if gebucht:
        _als_erloes_gebucht(s, a, "50.21", "9.54")
    _ebay_import(s, archiv, kontext, zweite=True)
    gleiche_auszahlungen_ab(s, kontext)
    (befund,) = _offene(s, "6009990001")
    if gebucht:
        assert befund.schweregrad is Schweregrad.FEHLER, befund.text
        assert _ustva_warnungen(s, "2026-09")
        _korrigiere_wie_vorgeschlagen(s, befund)
        gleiche_auszahlungen_ab(s, kontext)
        (befund,) = _offene(s, "6009990001")
    assert befund.code == "auszahlung_zweifel", befund.text
    befehl = f"accounti marktplatz zuordnen 6009990001 {str(a.id)[:8]}"
    assert befehl in befund.text
    ordne_zu(s, kontext, "6009990001", str(a.id)[:8], von="erika")
    assert _zugeordnet(s) == {"6009990001": a.id, "6009990002": b.id}
    assert {x.status for x in lade_abrechnungen(s)} == {AbrechnungStatus.ABGEGLICHEN}
    assert saldo(lade_buchungen(s), "1362") == 0
    assert not _offene(s, "6009990001") and not _offene(s, "6009990002")
    assert not _ustva_warnungen(s, "2026-09") and not _ustva_warnungen(s, "2026-10")


def test_zugeordneter_umsatz_nennt_eine_andere_bekannte_nummer(umgebung):
    """Regel 8: Die Zuordnung ist älter als die Nummer, die der Umsatz nennt (sie
    stand hinter einer Kundenangabe, Regel 4 hielt ihn nicht zurück) — sobald jene
    Abrechnung bekannt ist, sagt das ein Befund mit dem Befehl, der ihn dorthin
    ordnet."""
    s, archiv, kontext = umgebung
    b = bank(s, date(2026, 10, 2), "60.14", f"{EBAY} KD 6009990002", "eBay")
    (x,) = _ebay_import(s, archiv, kontext).abgleich
    assert x.transaktion is not None and x.transaktion.id == b.id
    _ebay_import(s, archiv, kontext, zweite=True)
    (befund,) = _offene(s, "6009990001")
    assert befund.code == "auszahlung_zweifel", befund.text
    befehl = f"accounti marktplatz zuordnen 6009990002 {str(b.id)[:8]}"
    assert befehl in befund.text
    ordne_zu(s, kontext, "6009990002", str(b.id)[:8], von="erika")
    assert _zugeordnet(s) == {"6009990002": b.id}
    assert not _offene(s, "6009990001") and not _offene(s, "6009990002")
    assert saldo(lade_buchungen(s), "1362") == Decimal(
        "59.73"
    )  # X wartet auf seine Bank


def test_loesen_haelt_den_umsatz_von_der_auszahlung_fern(umgebung):
    """``ordne_zu`` ohne Umsatz löst die Zuordnung: accountis Bankbuchung wird
    storniert, der Umsatz ist wieder offen, und der Abgleich nimmt ihn für diese
    Auszahlung nicht wieder (Hinweis an der Abrechnung)."""
    s, archiv, kontext = umgebung
    tx = bank(s, date(2026, 9, 3), "209.85", "AMAZON PAYMENTS EUROPE")
    (m,) = _amazon_september(s, archiv, kontext).abgleich
    assert m.transaktion is not None and m.transaktion.id == tx.id
    ergebnis = ordne_zu(s, kontext, "11223344556", None, von="erika")
    assert ergebnis.transaktion is None and ergebnis.geloest
    assert not buchungen_zur_transaktion(s, tx.id)
    assert not _zugeordnet(s)
    gleiche_auszahlungen_ab(s, kontext)
    assert not _zugeordnet(s)
    (a,) = lade_abrechnungen(s)
    assert any(b.code == "zuordnung_geloest" for b in a.offene_befunde)
    # ausdrücklich doch zuordnen geht
    ordne_zu(s, kontext, "11223344556", str(tx.id)[:8], von="erika")
    assert _zugeordnet(s) == {"11223344556": tx.id}


# --- N2: eigene Nummer außerhalb der Toleranz -------------------------------------


def test_eigene_nummer_gebucht_ausserhalb_der_toleranz_ist_befund(umgebung):
    """N2: A nennt 6009990001 und ist vor dem Import als Erlös gebucht; der Kurs der
    Abrechnung ist falsch (0,83 statt 0,865 — 62,25 € statt 59,73 €). Außerhalb der
    Toleranz gab es keinen Befund, die UStVA 09 schwieg bei doppeltem Erlös."""
    from accounti.integrationen.lauf import importiere

    s, archiv, kontext = umgebung
    a = bank(s, date(2026, 9, 30), "59.75", f"{EBAY} AUSZAHLUNG 6009990001", "eBay")
    _als_erloes_gebucht(s, a, "50.21", "9.54")
    (ergebnis,) = importiere(
        s, archiv, kontext, "ebay", _ebay_gbp(), "gbp1.csv", kurs=Decimal("0.8300")
    )
    (befund,) = [x.befund for x in ergebnis.abgleich if x.befund]
    assert befund.code == "auszahlung_anderweitig_gebucht", befund.text
    assert befund.schweregrad is Schweregrad.FEHLER
    assert "59,75" in befund.text
    (september,) = _ustva_warnungen(s, "2026-09")
    assert "30.09.2026" in september
    # nach der Korrektur steht er als Geldbewegung da — die Differenz bleibt ein
    # Fehler, bis der Kurs geklärt ist
    _korrigiere_wie_vorgeschlagen(s, befund)
    gleiche_auszahlungen_ab(s, kontext)
    (danach,) = _offene(s, "6009990001")
    assert danach.code == "auszahlung_abweichung", danach.text
    assert _ustva_warnungen(s, "2026-09")


# --- umstrittener Umsatz ohne Nummer: nicht raten ---------------------------------


def test_umsatz_ohne_nummer_fuer_zwei_abrechnungen_wird_nicht_geraten(umgebung):
    """Zwei eBay-Abrechnungen über je 100 € (EUR), auf der Bank zunächst nur einer
    ohne Nummer: beide hätten ihn als einzigen Kandidaten — wer zuerst kam, bekam
    ihn. Jetzt keiner; beide warnen mit dem Befehl."""
    from accounti.integrationen.lauf import importiere
    from tests.marktplatz_hilfe import ebay_bericht

    s, archiv, kontext = umgebung

    def bericht(nummer, tag):
        return ebay_bericht(
            (
                "24.09.2026",
                "Bestellung",
                f"12-{nummer[-1]}",
                "Deutschland",
                "100,00",
                nummer,
                "",
            ),
            ("30.09.2026", "Auszahlung", "", "", "-100,00", nummer, tag),
        )

    importiere(s, archiv, kontext, "ebay", bericht("6009990001", "30.09.2026"), "x")
    importiere(s, archiv, kontext, "ebay", bericht("6009990002", "01.10.2026"), "y")
    tx = bank(s, date(2026, 10, 1), "100.00", f"{EBAY} AUSZAHLUNG", "eBay")
    gleiche_auszahlungen_ab(s, kontext)
    assert not _zugeordnet(s)
    for nummer in ("6009990001", "6009990002"):
        (befund,) = _offene(s, nummer)
        assert befund.code == "auszahlung_mehrdeutig", befund.text
        assert f"accounti marktplatz zuordnen {nummer} {str(tx.id)[:8]}" in befund.text


def test_zuordnung_ohne_nummer_ist_ein_hinweis(umgebung):
    """Geraten ist nur, wo die Nummer fehlt — und dann sagt es ein Hinweis."""
    s, archiv, kontext = umgebung
    tx = bank(s, date(2026, 9, 3), "209.85", "AMAZON PAYMENTS EUROPE")
    _amazon_september(s, archiv, kontext)
    (a,) = lade_abrechnungen(s)
    (hinweis,) = [b for b in a.offene_befunde if b.code == "zuordnung_ohne_nummer"]
    assert hinweis.schweregrad is Schweregrad.HINWEIS
    assert str(tx.id)[:8] in hinweis.text and "marktplatz zuordnen" in hinweis.text


# --- CLI ----------------------------------------------------------------------------

runner = CliRunner()


def test_cli_marktplatz_zuordnen_mit_recht_buchen(tmp_path, monkeypatch):
    """``accounti marktplatz zuordnen`` wie die übrigen Buchungsbefehle: mit
    eingerichteten Benutzern nur mit dem Recht buchen (und Einmalcode); die Person
    steht im Journal."""
    from accounti.cli import app
    from accounti.integrationen.einstellungen import lade_kontext
    from accounti.models.auth import Rolle
    from accounti.pruefung.journal import lade_journal
    from tests.auth_hilfe import billige_hashes, lege_person_an, setze_schluessel

    billige_hashes(monkeypatch)
    setze_schluessel(monkeypatch)
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
            s, date(2026, 9, 3), "209.85", "AMAZON PAYMENTS EUROPE EREF 11223399999"
        )
        gleiche_auszahlungen_ab(s, kontext)
        s.commit()
        jetzt = datetime.now()
        lege_person_an(s, "jan", Rolle.BETRACHTER, jetzt=jetzt)
        eva = lege_person_an(s, "eva", Rolle.BUCHHALTER, jetzt=jetzt)
    engine.dispose()
    befehl = [
        "marktplatz",
        "zuordnen",
        "11223344556",
        str(tx.id)[:8],
        "--db",
        url,
        "--config",
        config,
    ]
    r = runner.invoke(app, [*befehl, "--von", "jan"])
    assert r.exit_code == 1 and "jan darf" in r.output, r.output
    monkeypatch.setenv("ACCOUNTI_EINMALCODE", eva.code(datetime.now()))
    r = runner.invoke(app, [*befehl, "--von", "eva"])
    assert r.exit_code == 0, r.output
    assert "zugeordnet" in r.output
    engine, make = session_factory(url)
    with make() as s:
        assert _zugeordnet(s) == {"11223344556": tx.id}
        (a,) = lade_abrechnungen(s)
        (p,) = [p for p in a.posten if p.bank_transaktion_id]
        (eintrag,) = lade_journal(s, objekt_id=str(p.id))
        assert "eva" in eintrag.person
    engine.dispose()


def test_ein_bericht_mit_zwei_abrechnungen_raet_auch_nicht(umgebung):
    """Wie oben, aber beide Auszahlungen in einem Bericht und der Umsatz schon auf
    der Bank: der Abgleich lief je Abrechnung beim Speichern — die erste nahm ihn,
    bevor die zweite gespeichert war. Jetzt gleicht der Import erst ab, wenn alle
    Abrechnungen des Berichts gespeichert sind."""
    from accounti.integrationen.lauf import importiere
    from tests.marktplatz_hilfe import ebay_bericht

    s, archiv, kontext = umgebung
    tx = bank(s, date(2026, 10, 1), "100.00", f"{EBAY} AUSZAHLUNG", "eBay")
    bericht = ebay_bericht(
        *(
            zeile
            for nummer, tag in (
                ("6009990001", "30.09.2026"),
                ("6009990002", "01.10.2026"),
            )
            for zeile in (
                (
                    "24.09.2026",
                    "Bestellung",
                    f"12-{nummer[-1]}",
                    "Deutschland",
                    "100,00",
                    nummer,
                    "",
                ),
                (tag, "Auszahlung", "", "", "-100,00", nummer, tag),
            )
        )
    )
    ergebnisse = importiere(s, archiv, kontext, "ebay", bericht, "xy.csv")
    assert len(ergebnisse) == 2
    assert not _zugeordnet(s)
    for e in ergebnisse:
        (m,) = e.abgleich
        assert m.befund is not None and m.befund.code == "auszahlung_mehrdeutig"
        assert str(tx.id)[:8] in m.befund.text


def test_import_ohne_bank_stichworte_warnt(umgebung):
    """Grenze aus der Simulation: ohne ``bank_stichworte`` erkennt der Abgleich eine
    Auszahlung in Fremdwährung ohne Nummer im Verwendungszweck nicht, und die
    Kontierung bucht sie nach den Regeln — der Import sagt das, statt still zu
    bleiben (``bank_stichworte: []`` ist für Gesellschaften ohne Marktplatz-Import)."""
    s, archiv, kontext = umgebung
    ergebnis = _ebay_import(s, archiv, _ohne_stichwort(kontext))
    (warnung,) = [
        b for b in ergebnis.abrechnung.befunde if b.code == "bank_stichworte_leer"
    ]
    assert warnung.schweregrad is Schweregrad.WARNUNG
    assert "integrationen.marktplaetze.ebay.bank_stichworte" in warnung.text
    mit = _ebay_import(s, archiv, kontext, zweite=True)
    assert not [b for b in mit.abrechnung.befunde if b.code == "bank_stichworte_leer"]


def test_zurueckgehaltener_umsatz_warnt_auch_ohne_stichwort(umgebung):
    """Simulation: ohne ``bank_stichworte`` hält Regel 4 einen Umsatz mit exakt dem
    Betrag zurück (Referenz mit dem Anfang der Nummern), die Warnung verlangte aber
    ein Stichwort — die Auszahlung blieb still offen. Die Warnung gilt für jeden
    Umsatz, der ohne die andere Nummer Treffer wäre."""
    s, archiv, kontext = umgebung
    kontext = _ohne_stichwort(kontext, "amazon")
    _amazon_september(s, archiv, kontext)
    tx = bank(s, date(2026, 9, 3), "209.85", "AMAZON PAYMENTS EUROPE EREF 11223399999")
    (m,) = gleiche_auszahlungen_ab(s, kontext)
    assert m.befund is not None and m.befund.code == "auszahlung_andere_nummer"
    assert str(tx.id)[:8] in m.befund.text


def _ebay_eur(nummer, tag, betrag="100,00"):
    from tests.marktplatz_hilfe import ebay_bericht

    return ebay_bericht(
        (
            "24.09.2026",
            "Bestellung",
            f"12-{nummer[-1]}",
            "Deutschland",
            betrag,
            nummer,
            "",
        ),
        (tag, "Auszahlung", "", "", f"-{betrag}", nummer, tag),
    )


def test_schon_gebucht_erledigt_sich_nach_der_korrektur_auch_wenn_mehrdeutig(umgebung):
    """Simulation (zwei eBay-Abrechnungen über je 100 €, Umsätze ohne Nummer): A ist
    als Erlös gebucht — „schon gebucht“ an 6009990001; B kommt offen, beide
    Abrechnungen haben ihn als einzigen Kandidaten (mehrdeutig). Nach der
    vorgeschlagenen Korrektur passen A und B (mehrdeutig) — der Fehler blieb offen,
    schlug die Korrektur einer stornierten Buchung vor, die UStVA 09 warnte weiter.
    Steht kein Erlös mehr da, ist er erledigt."""
    from accounti.integrationen.lauf import importiere

    s, archiv, kontext = umgebung
    a = bank(s, date(2026, 9, 30), "100.00", f"{EBAY} AUSZAHLUNG", "eBay")
    _als_erloes_gebucht(s, a, "84.03", "15.97")
    importiere(s, archiv, kontext, "ebay", _ebay_eur("6009990001", "30.09.2026"), "x")
    (befund,) = _offene(s, "6009990001")
    assert befund.code == "auszahlung_anderweitig_gebucht", befund.text
    bank(s, date(2026, 10, 1), "100.00", f"{EBAY} AUSZAHLUNG", "eBay")
    importiere(s, archiv, kontext, "ebay", _ebay_eur("6009990002", "01.10.2026"), "y")
    assert not _zugeordnet(s)
    assert {b.code for b in _offene(s, "6009990001")} == {
        "auszahlung_anderweitig_gebucht",
        "auszahlung_mehrdeutig",
    }
    _korrigiere_wie_vorgeschlagen(s, befund)
    gleiche_auszahlungen_ab(s, kontext)
    (danach,) = _offene(s, "6009990001")
    assert danach.code == "auszahlung_mehrdeutig", danach.text
    assert not _ustva_warnungen(s, "2026-09")
